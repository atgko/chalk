"""PDF rollover: a copy of the original PDF with only the dates and term
changed, so the rolled-over syllabus looks exactly like the one uploaded
(sponsor meeting, Oct 28).

A PDF syllabus is read once into a Word file (chalk.pdf_import), and the
Word rollover (chalk.rollover.docx_rollover) writes the new dates into a
copy of that file. Comparing the two Word files paragraph by paragraph
gives every piece of text rollover changed ("(1/13)" -> "(8/25)",
"Spring" -> "Fall") along with the words just before it. Each change is
found in the PDF's text (chalk.rollover.pdf_locate), and its glyphs are
rewritten in the PDF's own font (chalk.rollover.pdf_glyphs). Running
headers and footers the Word file left out get the new term too.

An embedded font is usually a subset: it only has the characters the
document uses. When the new text needs one it lacks (a syllabus with no
capital F can't spell "Fall"), the new text is drawn in the closest
standard PDF font instead (Helvetica, Times, or Courier, in the same
weight, size, and color).

Nothing is guessed: if a change can't be found, or the written PDF
doesn't read back as expected, no PDF is written and PdfRolloverError
says why. The Word file is always written, so the instructor still gets
a rolled-over syllabus. A course whose length or breaks change has rows
to add or remove, which a PDF can't do; the caller checks that first
(keeps_pdf_layout).
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from pypdf import PdfWriter
from pypdf.generic import ByteStringObject

from chalk.archiving import archive_before_write
from chalk.extractors.meetings import week_key
from chalk.models import CourseData
from chalk.rollover.pdf_glyphs import (
    Glyph,
    PageGlyphs,
    Removal,
    add_standard_font,
    advance,
    finish_page,
    kern,
    plan_removal,
    read_page_glyphs,
    remove_glyph_run,
    standard_font_width,
    text_operations,
)
from chalk.rollover.pdf_locate import (
    PdfRolloverError,
    PdfText,
    Target,
    expected_lines,
    locate,
    margin_term_targets,
    read_pdf_text,
)

__all__ = [
    "PdfRolloverError",
    "TextChange",
    "keeps_pdf_layout",
    "text_changes",
    "write_rolled_over_pdf",
]

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\s+|\S+")
# Words of context kept before a change, to find it in the PDF ("Week 2"
# before "(1/13)", so a "due (1/13)" elsewhere isn't changed instead).
_CONTEXT_WORDS = 2
# Up to this many unchanged words between two changes, or after the last
# one at the paragraph's end, are folded into the change.
_ABSORB_WORDS = 2
# A rewritten line may sit this much higher or lower when read back
# (points), since a standard font's ascent differs from the original's.
_LINE_TOLERANCE = 3.0
# Characters this close to a line's baseline (points) are on that line.
_BASELINE_TOLERANCE = 0.5
_SERIF_HINTS = ("times", "serif", "georgia", "cambria", "garamond", "book", "palatino", "minion")
_MONO_HINTS = ("courier", "mono", "consolas")


@dataclass(frozen=True)
class TextChange:
    """One piece of text the Word rollover changed, with the words just
    before it in its paragraph."""

    before: tuple[str, ...]
    old: str
    new: str


def keeps_pdf_layout(original: CourseData, rolled_over: CourseData) -> bool:
    """True when the rolled-over schedule has the same rows in the same
    order as the original — the same weeks and meetings, with each break
    between the same two weeks — so only text changes and a PDF copy can
    be written. A break that lands after a different week in the new term
    would move a row, which a PDF can't do."""
    return _rows(original) == _rows(rolled_over)


def _rows(course_data: CourseData) -> list:
    """The schedule's rows in date order: a week's key, or "break"."""
    weeks = list(course_data.weeks)
    if all((week.date or week.date_start) is not None for week in weeks):
        weeks.sort(key=lambda week: week.date or week.date_start)
    return ["break" if week.is_break else week_key(week) for week in weeks]


def write_rolled_over_pdf(
    original_pdf,
    source_docx,
    rolled_docx,
    output_path,
    *,
    old_term: str,
    new_term: str,
    eval_log_path=None,
) -> Path:
    """Write a copy of `original_pdf` with the changes between
    `source_docx` (the Word file read from it) and `rolled_docx` (its
    rollover) to `output_path`, archiving whatever was there first.
    Raises PdfRolloverError, writing nothing, if it can't be done exactly
    (including any unexpected failure reading or writing the PDF, so a
    PDF Chalk can't handle never stops the rest of the rollover)."""
    try:
        return _write_rolled_over_pdf(
            Path(original_pdf), source_docx, rolled_docx, Path(output_path),
            old_term=old_term, new_term=new_term, eval_log_path=eval_log_path,
        )  # fmt: skip
    except PdfRolloverError:
        raise
    except Exception as exc:
        logger.exception("The PDF copy of the rollover failed")
        raise PdfRolloverError("Chalk couldn't edit this PDF exactly.") from exc


def _write_rolled_over_pdf(
    original_pdf: Path, source_docx, rolled_docx, output_path: Path, *, old_term, new_term, eval_log_path
) -> Path:
    text = read_pdf_text(original_pdf)
    targets = locate(text_changes(source_docx, rolled_docx), text)
    if old_term != new_term:
        targets += margin_term_targets(text, targets, old_term, new_term)

    with tempfile.TemporaryDirectory(prefix="chalk-pdf-rollover-") as scratch:
        draft = Path(scratch) / "rolled-over.pdf"
        _write(original_pdf, text, targets, draft)
        _verify(draft, expected_lines(text, targets))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        archive_before_write(output_path, eval_log_path=eval_log_path)
        shutil.copyfile(draft, output_path)
    return output_path


# ---- What changed ------------------------------------------------------------------


def text_changes(source_docx, rolled_docx) -> list[TextChange]:
    """Every change between two Word files with the same paragraphs, in
    document order (tables included). Raises PdfRolloverError if a
    paragraph was added or removed."""
    before = _paragraph_texts(source_docx)
    after = _paragraph_texts(rolled_docx)
    if len(before) != len(after):
        raise PdfRolloverError(
            "The rolled-over schedule has rows the PDF doesn't, so Chalk can't keep the PDF's layout."
        )
    changes: list[TextChange] = []
    for old, new in zip(before, after):
        if old != new:
            changes += _paragraph_changes(old, new)
    return changes


def _paragraph_texts(docx_path) -> list[str]:
    body = Document(str(docx_path)).element.body
    return ["".join(t.text or "" for t in p.iter(qn("w:t"))) for p in body.iter(qn("w:p"))]


def _paragraph_changes(old: str, new: str) -> list[TextChange]:
    """Diff two versions of a paragraph word by word.

    A pure insertion is widened to the word before it, so every change
    replaces some old text that can be found in the PDF. Changes separated
    by only a little unchanged text — "(Jan." and "6)" in "(Jan. 6)", or
    "Spring" and the paragraph's end in "Spring 2026" — become one change
    covering it, so the new text is drawn as one piece with its own
    spacing (the PDF may place "2026" on its own, where it can't follow a
    shorter "Fall")."""
    old_tokens, new_tokens = _TOKEN_RE.findall(old), _TOKEN_RE.findall(new)
    spans: list[list[int]] = []  # [i1, i2, j1, j2]
    matcher = SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)
    opcodes = matcher.get_opcodes()
    for index, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if tag == "equal":
            continue
        if i1 == i2 and i1 > 0:  # an insertion: take the word before it along
            back = 1 if old_tokens[i1 - 1].strip() or i1 < 2 else 2
            i1, j1 = i1 - back, j1 - back
        if spans and _absorbable(old_tokens[spans[-1][1] : i1]):
            spans[-1][1:4:2] = [i2, j2]
        else:
            spans.append([i1, i2, j1, j2])
    if spans and _absorbable(old_tokens[spans[-1][1] :]):
        spans[-1][1], spans[-1][3] = len(old_tokens), len(new_tokens)

    changes = []
    for i1, i2, j1, j2 in spans:
        old_text, new_text = "".join(old_tokens[i1:i2]), "".join(new_tokens[j1:j2])
        if not old_text.strip():
            continue  # only spacing changed
        context = tuple(token for token in old_tokens[:i1] if token.strip())[-_CONTEXT_WORDS:]
        changes.append(TextChange(context, old_text.strip(), new_text.strip()))
    return changes


def _absorbable(tokens: list[str]) -> bool:
    """Unchanged text short enough to fold into the changes around it."""
    return sum(1 for token in tokens if token.strip()) <= _ABSORB_WORDS


# ---- Writing ------------------------------------------------------------------------


def _write(pdf_path: Path, text: PdfText, targets: list[Target], output: Path) -> None:
    writer = PdfWriter(clone_from=str(pdf_path))
    glyphs_by_page = {
        index: read_page_glyphs(page, writer) for index, page in enumerate(writer.pages)
    }
    codes_by_font = _learn_codes(glyphs_by_page, text)
    plans = [_plan(target, glyphs_by_page, codes_by_font, text, writer) for target in targets]
    drawings: dict[int, list] = {}
    # Last run first on each page: rewriting an operator leaves everything
    # drawn before the rewritten glyphs where it was.
    for plan in sorted(plans, key=lambda plan: (plan.page, *_order(plan.run[0])), reverse=True):
        page_glyphs = glyphs_by_page[plan.page]
        remove_glyph_run(page_glyphs, plan.run, plan.removal)
        drawn_at = plan.run[0].moved(_shift_before(plan, plans))
        drawings.setdefault(plan.page, []).extend(
            text_operations(drawn_at, plan.elements, plan.font_name, plan.color, page_glyphs.offset)
        )
    for index, drawing in drawings.items():
        finish_page(glyphs_by_page[index], drawing)
        writer.pages[index].replace_contents(glyphs_by_page[index].content)
    with output.open("wb") as handle:
        writer.write(handle)


@dataclass(frozen=True)
class _Plan:
    """One replacement, worked out before the page is changed: the glyphs
    to remove, how to draw the new text, and the gaps that leaves."""

    page: int
    run: list[Glyph]
    elements: list  # the new text as TJ elements
    font_name: str
    color: tuple
    removal: Removal


def _plan(target: Target, glyphs_by_page: dict, codes_by_font: dict, text: PdfText, writer) -> _Plan:
    page_glyphs = glyphs_by_page[target.page]
    run = _glyph_run(page_glyphs, target)
    elements, font_name, width = _new_text(target, run[0], codes_by_font, writer.pages[target.page])
    run = _with_covered_spaces(run, width, page_glyphs, text.chars[target.page])
    color = _color(target.chars[0].get("non_stroking_color"))
    return _Plan(target.page, run, elements, font_name, color, plan_removal(page_glyphs, run, width))


def _shift_before(plan: _Plan, plans: list[_Plan]) -> float:
    """How far earlier changes in the same flow of text move this one:
    a longer or shorter date before it on the line pushes it along."""
    first = plan.run[0]
    return sum(
        other.removal.shift
        for other in plans
        if other.page == plan.page
        and other.run[0].flow == first.flow
        and _order(other.run[0]) < _order(first)
    )


def _with_covered_spaces(
    run: list[Glyph], width: float, page_glyphs: PageGlyphs, chars: list[dict]
) -> list[Glyph]:
    """The run plus any space glyph the new text will cover. A longer
    date can reach past a space the PDF draws on its own after the old
    one, and text extraction would then read "(8/24 )"."""
    x, y = run[0].origin
    reach = x + width * run[0].to_page[0]
    covered = [
        page_glyphs.at(char["matrix"][4], char["matrix"][5])
        for char in chars
        if not char["text"].strip()
        and abs(char["matrix"][5] - y) < _BASELINE_TOLERANCE
        and x < char["matrix"][4] < reach
    ]
    extra = [glyph for glyph in covered if glyph is not None and glyph not in run]
    return sorted([*run, *extra], key=_order) if extra else run


def _new_text(target: Target, glyph: Glyph, codes_by_font: dict, page) -> tuple[list, str, float]:
    """How to draw the target's new text: TJ elements, the font's resource
    name, and its width in text space. In the old text's own font when it
    has every character; otherwise in the closest standard font."""
    known = codes_by_font.get(glyph.font.key, {})
    if all(char in known or char == " " for char in target.new):
        elements: list = []
        width = 0.0
        for word_index, word in enumerate(target.new.split(" ")):
            if word_index:  # a space: the font's own, or a gap as wide as one
                if " " in known:
                    elements.append(ByteStringObject(glyph.font.encode([known[" "]])))
                    width += advance(glyph, known[" "])
                else:
                    space = glyph.font.default_width / 1000 * glyph.font_size * glyph.h_scale
                    elements.append(kern(space, glyph))
                    width += space
            codes = [known[char] for char in word]
            if codes:
                elements.append(ByteStringObject(glyph.font.encode(codes)))
                width += sum(advance(glyph, code) for code in codes)
        return elements, glyph.font_name, width
    base_font = standard_font(target.chars[0]["fontname"])
    elements = [ByteStringObject(target.new.encode("cp1252", "replace"))]
    return (
        elements,
        add_standard_font(page, base_font),
        standard_font_width(target.new, base_font, glyph),
    )


def _glyph_run(page_glyphs: PageGlyphs, target: Target) -> list[Glyph]:
    run = []
    for char in target.chars:
        glyph = page_glyphs.at(char["matrix"][4], char["matrix"][5])
        if glyph is None:
            raise PdfRolloverError(
                f"Chalk found \"{char['text']}\" in the PDF but can't edit how it's drawn."
            )
        run.append(glyph)
    return sorted(run, key=_order)


def _order(glyph: Glyph) -> tuple[int, int, int]:
    return glyph.op_index, glyph.element, glyph.code_index


def _learn_codes(glyphs_by_page: dict[int, PageGlyphs], text: PdfText) -> dict[str, dict[str, int]]:
    """Which code draws which character in each font, learned by matching
    every glyph to the character pdfplumber read at the same position. An
    embedded font is usually a subset with its own codes, so this is the
    only reliable way to write new text in it."""
    codes: dict[str, dict[str, int]] = {}
    for index, chars in enumerate(text.chars):
        for char in chars:
            glyph = glyphs_by_page[index].at(char["matrix"][4], char["matrix"][5])
            if glyph is not None and len(char["text"]) == 1:
                codes.setdefault(glyph.font.key, {}).setdefault(char["text"], glyph.code)
    return codes


def standard_font(fontname: str) -> str:
    """The standard PDF font closest to an embedded one: "ABCDEF+Calibri,Bold"
    -> "Helvetica-Bold", "TimesNewRomanPS-ItalicMT" -> "Times-Italic"."""
    name = fontname.split("+")[-1].lower()
    bold = any(word in name for word in ("bold", "black", "heavy", "semibold"))
    italic = "italic" in name or "oblique" in name
    if any(hint in name for hint in _MONO_HINTS):
        family, styles = "Courier", ("", "-Bold", "-Oblique", "-BoldOblique")
    elif any(hint in name for hint in _SERIF_HINTS) and "sans" not in name:
        family, styles = "Times", ("-Roman", "-Bold", "-Italic", "-BoldItalic")
    else:
        family, styles = "Helvetica", ("", "-Bold", "-Oblique", "-BoldOblique")
    return family + styles[bold + 2 * italic]


def _color(color) -> tuple:
    """pdfplumber's fill color as gray, RGB, or CMYK numbers; black when
    it's a pattern or missing."""
    values = tuple(float(value) for value in (color or ()) if isinstance(value, (int, float)))
    return values if len(values) in (1, 3, 4) else (0.0,)


def _verify(draft: Path, expected: dict[tuple[int, float], str]) -> None:
    """Read the written PDF back and check every changed line reads as
    expected."""
    lines = read_pdf_text(draft).lines
    for (page, top), text in expected.items():
        if not any(
            line.page == page and abs(line.top - top) <= _LINE_TOLERANCE and line.compact == text
            for line in lines
        ):
            raise PdfRolloverError(
                "The edited PDF didn't read back as expected, so Chalk didn't keep it."
            )
