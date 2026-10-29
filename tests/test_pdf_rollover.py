"""The PDF rollover: a copy of the original PDF with only the changed text
rewritten (chalk.rollover.pdf_rollover, pdf_locate, pdf_glyphs)."""

from pathlib import Path

import pdfplumber
import pytest
from docx import Document
from pypdf import PdfReader
from pypdf.generic import ContentStream
from reportlab.pdfbase.pdfmetrics import stringWidth

from chalk.pipeline import (
    confirm_rollover,
    extract_syllabus,
    preview_rollover,
    save_reviewed_course,
)
from chalk.rollover.pdf_glyphs import raw_bytes
from chalk.rollover.pdf_rollover import (
    PdfRolloverError,
    TextChange,
    keeps_pdf_layout,
    standard_font,
    text_changes,
    write_rolled_over_pdf,
)
from tests.fixtures.pdf_layout_builder import PAGE_HEIGHT, PageBuilder, build_pdf
from tests.sample_course import build_sample_course_data


def _docx(path: Path, paragraphs: list[str]) -> Path:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(str(path))
    return path


def _pair(tmp_path: Path, before: list[str], after: list[str]) -> tuple[Path, Path]:
    return _docx(tmp_path / "source.docx", before), _docx(tmp_path / "rolled.docx", after)


def _syllabus_pdf(path: Path, *, footer: str = "IS 6640 | Page 1") -> Path:
    page = PageBuilder()
    page.lines(72, 60, ["Networking and Servers", "IS 6640 | Fall 2026"])
    page.table(
        72,
        120,
        [90, 200],
        [
            [["Week"], ["Topics"]],
            [["Week 1 (8/24)"], ["Course introduction, due 8/31"]],
            [["Week 2 (8/31)"], ["Subnetting"]],
        ],
    )
    page.text(72, 760, footer)
    return build_pdf(path, [page])


def _lines(pdf_path: Path, page: int = 0) -> list[str]:
    with pdfplumber.open(pdf_path) as pdf:
        return [line["text"] for line in pdf.pages[page].extract_text_lines()]


def _rollover(tmp_path, pdf, before, after, *, old_term="Fall 2026", new_term="Fall 2027") -> Path:
    source, rolled = _pair(tmp_path, before, after)
    return write_rolled_over_pdf(
        pdf, source, rolled, tmp_path / "out" / "syllabus.pdf", old_term=old_term, new_term=new_term
    )


# ---- What changed -------------------------------------------------------------------


def test_text_changes_keep_the_words_before_each_change(tmp_path):
    source, rolled = _pair(
        tmp_path, ["Intro", "Week 2 (1/13)", "Unchanged"], ["Intro", "Week 2 (8/31)", "Unchanged"]
    )
    assert text_changes(source, rolled) == [TextChange(("Week", "2"), "(1/13)", "(8/31)")]


def test_nearby_changes_and_a_short_ending_become_one_change(tmp_path):
    source, rolled = _pair(
        tmp_path,
        ["Week 1 (Jan. 6)", "OSC 6660 | Spring 2026", "Spring 2026 classes begin on time"],
        ["Week 1 (Aug. 24)", "OSC 6660 | Fall 2026", "Fall 2026 classes begin on time"],
    )
    assert text_changes(source, rolled) == [
        TextChange(("Week", "1"), "(Jan. 6)", "(Aug. 24)"),
        TextChange(("6660", "|"), "Spring 2026", "Fall 2026"),
        TextChange((), "Spring", "Fall"),
    ]


def test_an_insertion_takes_the_word_before_it(tmp_path):
    source, rolled = _pair(tmp_path, ["Week 3 (9/7) and more words here"], ["Week 3 (9/7) Labs and more words here"])
    assert text_changes(source, rolled) == [TextChange(("Week", "3"), "(9/7)", "(9/7) Labs")]


def test_a_spacing_only_change_is_ignored(tmp_path):
    source, rolled = _pair(tmp_path, ["Week 1  (8/24) and the rest"], ["Week 1 (8/24) and the rest"])
    assert text_changes(source, rolled) == []


def test_added_rows_mean_the_layout_cant_be_kept(tmp_path):
    source, rolled = _pair(tmp_path, ["Week 1 (8/24)"], ["Week 1 (8/23)", "Week 2 (8/30)"])
    with pytest.raises(PdfRolloverError, match="rows the PDF doesn't"):
        text_changes(source, rolled)


def test_keeps_pdf_layout_compares_weeks_and_breaks():
    course = build_sample_course_data()
    shorter = course.model_copy(update={"weeks": course.weeks[:-1]})
    assert keeps_pdf_layout(course, course)
    assert not keeps_pdf_layout(course, shorter)


@pytest.mark.parametrize(
    ("fontname", "expected"),
    [
        ("WRTXTL+Calibri,Bold", "Helvetica-Bold"),
        ("AAAAAA+TimesNewRomanPSMT", "Times-Roman"),
        ("TimesNewRomanPS-BoldItalicMT", "Times-BoldItalic"),
        ("Georgia-Italic", "Times-Italic"),
        ("Arial-ItalicMT", "Helvetica-Oblique"),
        ("CourierNewPS-BoldMT", "Courier-Bold"),
        ("NotoSansSerif", "Helvetica"),
    ],
)
def test_standard_font_is_the_closest_family_and_style(fontname, expected):
    assert standard_font(fontname) == expected


# ---- Writing the PDF ----------------------------------------------------------------


def test_dates_and_term_change_and_everything_else_stays(tmp_path):
    pdf = _syllabus_pdf(tmp_path / "s.pdf", footer="IS 6640 | Fall 2026 | Page 1")
    before = _lines(pdf)

    out = _rollover(
        tmp_path,
        pdf,
        ["IS 6640 | Fall 2026", "Week 1 (8/24)", "Week 2 (8/31)"],
        ["IS 6640 | Fall 2027", "Week 1 (8/23)", "Week 2 (8/30)"],
    )

    after = _lines(out)
    assert "IS 6640 | Fall 2027" in after
    assert "IS 6640 | Fall 2027 | Page 1" in after  # the running footer too
    assert any(line.startswith("Week 1 (8/23)") and "due 8/31" in line for line in after)
    assert any(line.startswith("Week 2 (8/30)") for line in after)
    assert after[0] == before[0] == "Networking and Servers"
    assert len(after) == len(before)


def test_a_date_wrapped_onto_the_next_line_of_its_cell_is_found(tmp_path):
    page = PageBuilder()
    page.text(72, 60, "IS 6640 | Fall 2026")
    page.table(72, 120, [90, 200], [[["Week"], ["Topics"]], [["Week 1", "(Jan. 6)"], ["Introduction"]]])
    pdf = build_pdf(tmp_path / "wrapped.pdf", [page])

    out = _rollover(tmp_path, pdf, ["Week 1 (Jan. 6)"], ["Week 1 (Aug. 24)"])

    assert any(line.startswith("(Aug. 24)") for line in _lines(out))


def test_a_character_the_font_never_draws_is_written_in_a_standard_font(tmp_path):
    pdf = _syllabus_pdf(tmp_path / "s.pdf")
    out = _rollover(tmp_path, pdf, ["Week 1 (8/24)"], ["Week 1 (@8/23)"])

    assert any(line.startswith("Week 1 (@8/23)") for line in _lines(out))
    fonts = PdfReader(out).pages[0]["/Resources"]["/Font"]
    assert "/ChalkHelvetica" in fonts


def test_glyphs_clipped_one_by_one_are_redrawn_outside_every_clip(tmp_path):
    """Some PDF printers clip each glyph to its own narrow box, which
    would hide a longer date written in its place."""
    page = PageBuilder()
    page.text(72, 60, "IS 6640 | Fall 2026")
    x, top = 80.0, 200
    for char in "Week 1 (8/24)":
        baseline = PAGE_HEIGHT - top - 10
        escaped = char.replace("(", "\\(").replace(")", "\\)")
        width = stringWidth(char, "Helvetica", 10)
        page.ops.append(f"q {x} {baseline - 3} {width} 14 re W n BT /F1 10 Tf {x} {baseline} Td ({escaped}) Tj ET Q")
        x += width
    page.ops.append("q")  # left open: the redrawn text must still escape it
    pdf = build_pdf(tmp_path / "clipped.pdf", [page])

    out = _rollover(tmp_path, pdf, ["Week 1 (8/24)"], ["Week 1 (12/31)"])

    reader = PdfReader(out)
    operations = ContentStream(reader.pages[0].get_contents(), reader).operations
    depth, depth_at_text = 0, []
    for operands, operator in operations:
        depth += {b"q": 1, b"Q": -1}.get(operator, 0)
        shown = b"".join(raw_bytes(e) for e in operands[0] if isinstance(e, (bytes, str))) if operator == b"TJ" else b""
        if b"12/31" in shown:
            depth_at_text.append(depth)
    assert depth_at_text == [0]
    assert any(line.startswith("Week 1 (12/31)") for line in _lines(out))


def test_text_the_pdf_doesnt_have_writes_nothing(tmp_path):
    pdf = _syllabus_pdf(tmp_path / "s.pdf")
    with pytest.raises(PdfRolloverError, match="couldn't find"):
        _rollover(tmp_path, pdf, ["Week 9 (10/19)"], ["Week 9 (10/18)"])
    assert not (tmp_path / "out" / "syllabus.pdf").exists()


def test_a_second_rollover_archives_the_first(tmp_path):
    pdf = _syllabus_pdf(tmp_path / "s.pdf")
    _rollover(tmp_path, pdf, ["Week 1 (8/24)"], ["Week 1 (8/23)"])
    _rollover(tmp_path, pdf, ["Week 1 (8/24)"], ["Week 1 (8/22)"])

    assert list((tmp_path / "out" / ".archive").glob("syllabus-*.pdf"))
    assert any(line.startswith("Week 1 (8/22)") for line in _lines(tmp_path / "out" / "syllabus.pdf"))


# ---- The real syllabi, when they're on this computer --------------------------------

_IS_4440 = Path(__file__).parent.parent / "reference" / "IS-4440 16-Week Course Syllabus.pdf"


@pytest.mark.skipif(not _IS_4440.is_file(), reason="reference/ is git-ignored; real syllabi are local only")
def test_the_is_4440_syllabus_rolls_over_as_a_pdf(tmp_project):
    course_data, _ = extract_syllabus(tmp_project, _IS_4440)
    save_reviewed_course(tmp_project, course_data)
    plan = preview_rollover(tmp_project, course_data, "Fall 2026", llm_generate_topics=False)
    written = confirm_rollover(tmp_project, plan)

    pdf = tmp_project.syllabus_output("pdf")
    assert pdf in written
    text = "\n".join(_lines(pdf, 0) + _lines(pdf, 7))
    assert "IS 4440-001, Fall 2026" in text
    assert "Week 1 (8/24)" in text
