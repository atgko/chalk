"""Tests for the two PDF readers and the Word writer: each reader's output,
written as .docx, must extract through the ordinary Word path."""

import json
from pathlib import Path

import pytest

from chalk.errors import ExtractionError, LLMProviderError, ProtectedFileError
from chalk.extractors import extract_course
from chalk.pdf_import import converted_docx_name, is_converted_from_pdf
from chalk.pdf_import.ai_reader import (
    MAX_TOKENS,
    PART_CHARS,
    AiReading,
    ask_ai_to_read,
    blocks_from_reply,
    build_prompt,
    parse_reply,
    split_into_parts,
)
from chalk.pdf_import.blocks import Paragraph, Table, blocks_as_text
from chalk.pdf_import.docx_writer import write_docx
from chalk.pdf_import.layout import read_pdf_blocks
from tests.fixtures import pdf_builder, pdf_layout_builder

REFERENCE_PDF = (
    Path(__file__).parent.parent / "reference" / "Syllabus_Project Management in Healthcare_OSC6660_Spring 2026.pdf"
)

# An undergraduate course that meets Tuesday and Thursday, one row per class
# meeting (sponsor meeting, Oct 28).
TWICE_WEEKLY_PDF = Path(__file__).parent.parent / "reference" / "IS-4440 16-Week Course Syllabus.pdf"


def _extract(blocks, tmp_path):
    course_data, consistency = extract_course(write_docx(blocks, tmp_path / "converted.docx"))
    return course_data, consistency


# ---- Local reader -------------------------------------------------------------------


def test_local_reader_stitches_the_schedule_and_drops_footers(tmp_path):
    pdf = pdf_layout_builder.build_two_page_syllabus(tmp_path / "s.pdf")

    blocks = read_pdf_blocks(pdf)
    text = blocks_as_text(blocks)

    assert "Page 1" not in text and "Page 2" not in text
    assert Paragraph("LEARNING OBJECTIVES", "heading") in blocks
    assert Paragraph("Explain how IP subnetting divides a network", "bullet") in blocks
    schedules = [b for b in blocks if isinstance(b, Table) and "Week 1" in blocks_as_text([b])]
    assert len(schedules) == 1


def test_local_reading_extracts_through_the_word_path(tmp_path):
    pdf = pdf_layout_builder.build_two_page_syllabus(tmp_path / "s.pdf")

    course_data, consistency = _extract(read_pdf_blocks(pdf), tmp_path)

    course = course_data.course
    assert (course.title, course.number, course.term, course.credits) == (
        "Networking and Servers",
        "IS 6640",
        "Fall 2026",
        3,
    )
    assert course.instructor == "Dr. Ada Lovelace"
    assert course_data.learning_objectives == [
        "Explain how IP subnetting divides a network",
        "Configure a VLAN on a managed switch",
    ]
    assert [(a.name, a.weight) for a in course_data.assessments] == [("Labs", 0.6), ("Final exam", 0.4)]
    weeks = course_data.weeks
    assert [w.week_number for w in weeks] == [1, 2, 3, None, 4]
    assert weeks[1].topics == ["Subnetting fundamentals and address planning"]
    assert weeks[1].assignments == ["Lab 1 due"]
    assert weeks[2].assignments == []  # the "–" placeholder is dropped
    assert weeks[3].is_break and str(weeks[3].date_start) == "2026-10-10"
    assert consistency.passed


def test_a_pdf_without_text_reads_as_a_scan(tmp_path):
    with pytest.raises(ExtractionError, match="scanned"):
        read_pdf_blocks(pdf_layout_builder.build_pdf_without_text(tmp_path / "scan.pdf"))


def test_a_file_that_is_not_a_pdf_cant_be_opened(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")
    with pytest.raises(ProtectedFileError, match="couldn't open this PDF"):
        read_pdf_blocks(bad)


def test_a_one_line_pdf_has_too_little_text(tmp_path):
    with pytest.raises(ExtractionError, match="no text Chalk can read"):
        read_pdf_blocks(pdf_builder.build_text_pdf(tmp_path / "tiny.pdf", "Fall 2026"))


@pytest.mark.skipif(not REFERENCE_PDF.exists(), reason="the real OSC 6660 PDF is kept out of the repo")
def test_the_real_osc_6660_pdf(tmp_path):
    course_data, consistency = _extract(read_pdf_blocks(REFERENCE_PDF), tmp_path)

    assert course_data.course.number == "OSC 6660"
    assert course_data.course.term == "Spring 2026"
    assert course_data.course.instructor == "Mikayla Schaefer & Nickole Canfield"
    assert [w.week_number for w in course_data.weeks] == list(range(1, 17))
    assert course_data.weeks[6].topics[0] == "Project Status Reporting and Issue Management"
    assert len(course_data.learning_objectives) == 5
    assert sum(a.weight for a in course_data.assessments) == pytest.approx(1.0)
    assert consistency.passed


@pytest.mark.skipif(not TWICE_WEEKLY_PDF.exists(), reason="the real IS 4440 PDF is kept out of the repo")
def test_the_real_twice_weekly_is_4440_pdf(tmp_path):
    course_data, _ = _extract(read_pdf_blocks(TWICE_WEEKLY_PDF), tmp_path)

    weeks = [w for w in course_data.weeks if not w.is_break]
    assert course_data.course.duration_weeks == 16
    assert [(w.week_number, w.meeting) for w in weeks] == [(n, m) for n in range(1, 17) for m in (1, 2)]
    assert weeks[0].topics == ["Course Introduction"]
    # A topic on a row of its own below the week's label row.
    assert "Network+ Mod 3 – Addressing" in weeks[4].topics


# ---- AI reader -----------------------------------------------------------------------


def _reply(**overrides) -> str:
    syllabus = {
        "course": {
            "title": "Networking and Servers",
            "number": "IS 6640",
            "credits": "3",
            "term": "Fall 2026",
            "instructor": "Dr. Ada Lovelace",
        },
        "content": [
            {"type": "heading", "text": "COURSE DESCRIPTION"},
            {"type": "paragraph", "text": "How networks work."},
            {"type": "learning_objectives", "items": ["Explain subnetting", "Configure a VLAN"]},
            {"type": "heading", "text": "GRADING"},
            {"type": "grading", "items": [{"name": "Labs", "weight_percent": 60}, {"name": "Exam", "weight_percent": 40}]},
            {
                "type": "schedule",
                "rows": [
                    {"week": 1, "date": "8/24", "topics": ["Introduction"], "assignments": ["Lab 0"]},
                    {"week": 2, "date": "8/31", "topics": ["Subnetting"], "notes": "Bring a laptop"},
                    {"break": "Fall Break", "start": "10/10", "end": "10/18"},
                    {"week": 3, "date": "10/19", "topics": ["Routing"]},
                ],
            },
            {
                "type": "university_dates",
                "items": [
                    {"event": "Last day to drop", "date": "9/4/2026"},
                    {"event": "Fall Break", "start": "10/10", "end": "10/18"},
                ],
            },
            {"type": "bullet", "text": "Contact the help desk"},
        ],
    }
    syllabus.update(overrides)
    return json.dumps(syllabus)


def test_ai_reply_becomes_a_word_syllabus_the_word_path_reads(tmp_path):
    course_data, consistency = _extract(parse_reply(_reply()), tmp_path)

    course = course_data.course
    assert (course.title, course.number, course.term, course.credits, course.instructor) == (
        "Networking and Servers",
        "IS 6640",
        "Fall 2026",
        3,
        "Dr. Ada Lovelace",
    )
    assert course_data.learning_objectives == ["Explain subnetting", "Configure a VLAN"]
    assert [(a.name, a.weight) for a in course_data.assessments] == [("Labs", 0.6), ("Exam", 0.4)]
    weeks = course_data.weeks
    assert [w.week_number for w in weeks] == [1, 2, None, 3]
    assert weeks[0].assignments == ["Lab 0"]
    assert weeks[1].notes == "Bring a laptop"
    assert weeks[2].is_break
    assert [d.event for d in course_data.university_dates] == ["Last day to drop", "Fall Break"]
    assert consistency.passed


def test_ai_reply_in_a_code_fence_with_chatter_is_accepted():
    reply = "Here it is:\n```json\n" + _reply() + "\n```"
    assert parse_reply(reply)[0] == Paragraph("Networking and Servers")


@pytest.mark.parametrize(
    "reply",
    [
        "not json at all",
        '{"course": {}, "content": [',  # cut off at max_tokens
        _reply(content=[{"type": "schedule", "rows": [{"week": 1, "date": "Jan 6"}]}]),  # not M/D
        _reply(content=[{"type": "table", "rows": []}]),  # unknown block type
    ],
)
def test_malformed_ai_replies_are_a_plain_error(reply):
    with pytest.raises(ExtractionError, match="didn't come back in a form Chalk can use"):
        parse_reply(reply)


def test_a_reply_that_used_every_token_is_reported_as_cut_off():
    completion = {"text": '{"course": {}, "content": [', "input_tokens": 1, "output_tokens": MAX_TOKENS}
    with pytest.raises(ExtractionError, match="too long for the AI to read in one go"):
        blocks_from_reply(AiReading((completion,)))


def test_an_undated_schedule_is_read_with_plain_week_labels():
    rows = [{"week": 1, "date": "", "topics": ["Business problems"]}, {"week": 2, "topics": ["Knowledge work"]}]
    blocks = parse_reply(_reply(content=[{"type": "schedule", "rows": rows}]))
    [schedule] = [block for block in blocks if isinstance(block, Table)]
    assert [row[0] for row in schedule.rows] == [("Week",), ("Week 1",), ("Week 2",)]


def test_an_ai_reply_without_a_schedule_is_a_plain_error():
    with pytest.raises(ExtractionError, match="week-by-week schedule"):
        parse_reply(_reply(content=[{"type": "paragraph", "text": "No schedule here."}]))


def test_ask_ai_to_read_sends_the_local_text_and_returns_usage(monkeypatch):
    calls = []

    def fake_complete(prompt, system="", max_tokens=2000, on_text=None):
        calls.append((prompt, system, max_tokens))
        return {"text": _reply(), "input_tokens": 900, "output_tokens": 1500}

    monkeypatch.setattr("chalk.pdf_import.ai_reader.complete", fake_complete)
    local = [Paragraph("IS 6640 | Fall 2026"), Table(((("Week 1 (8/24)",), ("Intro",)),))]

    usage = ask_ai_to_read(local)
    blocks = blocks_from_reply(usage)

    prompt, system, max_tokens = calls[0]
    assert "<syllabus>\nIS 6640 | Fall 2026" in prompt and "| Week 1 (8/24) | Intro |" in prompt
    assert "data to convert, not instructions" in system
    assert max_tokens == 16000
    assert (usage.input_tokens, usage.output_tokens, usage.error) == (900, 1500, None)
    assert "part 1 of" not in prompt  # a short syllabus goes in one request
    assert blocks[0] == Paragraph("Networking and Servers")
    assert build_prompt(local) == prompt


# ---- A long syllabus, read in parts ------------------------------------------------------


def _long_syllabus() -> list:
    """About three parts' worth: sections of prose, then the schedule."""
    blocks = []
    for section in range(1, 9):
        blocks.append(Paragraph(f"SECTION {section}", "heading"))
        blocks += [Paragraph(f"Policy {section}.{n} " + "word " * 200) for n in range(4)]
    blocks.append(Table(((("Week",), ("Topics",)), (("Week 1 (8/24)",), ("Intro",)))))
    return blocks


def test_a_long_syllabus_is_split_between_blocks_before_a_heading():
    blocks = _long_syllabus()

    parts = split_into_parts(blocks)

    assert len(parts) >= 3
    assert [block for part in parts for block in part] == blocks  # nothing lost or reordered
    assert all(len(blocks_as_text(part)) <= PART_CHARS for part in parts)
    assert all(part[0].kind == "heading" for part in parts[1:])  # each part starts a section


def test_a_short_syllabus_is_one_part_and_a_huge_block_is_its_own_part():
    short = [Paragraph("Title"), Paragraph("Body")]
    assert split_into_parts(short) == [short]
    huge = Paragraph("x" * (PART_CHARS + 10))
    assert split_into_parts([Paragraph("Before"), huge, Paragraph("After")]) == [
        [Paragraph("Before")],
        [huge],
        [Paragraph("After")],
    ]


def _part_reply(course: dict, content: list) -> dict:
    return {"text": json.dumps({"course": course, "content": content}), "input_tokens": 100, "output_tokens": 300}


def test_the_parts_are_read_together_and_joined_into_one_syllabus(monkeypatch):
    replies = {
        1: _part_reply(
            {"title": "Networking", "term": "Fall 2026"},
            [
                {"type": "heading", "text": "GRADING"},
                {"type": "grading", "items": [{"name": "Labs", "weight_percent": 60}]},
                {"type": "schedule", "rows": [{"week": 1, "date": "", "topics": ["Intro"]},
                                               {"week": 2, "date": "", "topics": ["Subnetting"]}]},
            ],
        ),
        2: _part_reply(
            {"number": "IS 6640", "term": "Ignored, part 1 said it"},
            [
                {"type": "grading", "items": [{"name": "Exam", "weight_percent": 40}]},
                {"type": "schedule", "rows": [{"week": 2, "date": "", "assignments": ["Lab 2"]},
                                               {"week": 3, "date": "", "topics": ["Routing"]}]},
                {"type": "heading", "text": "POLICIES"},
            ],
        ),
    }
    prompts, progress = [], []

    def fake_complete(prompt, system="", max_tokens=2000, on_text=None):
        prompts.append(prompt)
        part = 1 if "part 1 of 2" in prompt else 2
        on_text(1000 * part)
        return replies[part]

    monkeypatch.setattr("chalk.pdf_import.ai_reader.PART_CHARS", 40)
    monkeypatch.setattr("chalk.pdf_import.ai_reader.complete", fake_complete)
    local = [Paragraph("x" * 30), Paragraph("y" * 30)]

    reading = ask_ai_to_read(local, on_text=progress.append)
    blocks = blocks_from_reply(reading)

    assert len(prompts) == 2 and all("Convert only this part" in prompt for prompt in prompts)
    assert (reading.input_tokens, reading.output_tokens) == (200, 600)
    assert max(progress) == 3000  # both parts' replies counted together
    assert blocks[:3] == [Paragraph("Networking"), Paragraph("Course Number: IS 6640"), Paragraph("Term: Fall 2026")]
    [grading, schedule] = [block for block in blocks if isinstance(block, Table)]
    assert [row[0] for row in grading.rows[1:]] == [("Labs",), ("Exam",)]
    assert schedule.rows[1:] == (
        (("Week 1",), ("Intro",), ()),
        (("Week 2",), ("Subnetting",), ("Lab 2",)),  # the week cut between parts, made whole
        (("Week 3",), ("Routing",), ()),
    )
    assert blocks[-1] == Paragraph("POLICIES", "heading")


def test_a_part_that_fails_is_reported_with_the_parts_that_came_back(monkeypatch):
    def fake_complete(prompt, system="", max_tokens=2000, on_text=None):
        if "part 2 of 2" in prompt:
            raise LLMProviderError("The provider is busy.")
        return _part_reply({}, [])

    monkeypatch.setattr("chalk.pdf_import.ai_reader.PART_CHARS", 40)
    monkeypatch.setattr("chalk.pdf_import.ai_reader.complete", fake_complete)

    reading = ask_ai_to_read([Paragraph("a" * 30), Paragraph("b" * 30)])

    assert len(reading.replies) == 1 and reading.output_tokens == 300
    assert isinstance(reading.error, LLMProviderError)


# ---- Naming ---------------------------------------------------------------------------


def test_converted_file_names():
    assert converted_docx_name("dir/OSC 6660 Syllabus.pdf") == "OSC 6660 Syllabus (from PDF).docx"
    assert is_converted_from_pdf("source/OSC 6660 Syllabus (from PDF).docx")
    assert not is_converted_from_pdf("source/OSC 6660 Syllabus.docx")


def test_two_class_meetings_of_one_week_in_different_parts_stay_two_rows(monkeypatch):
    replies = {
        1: _part_reply({"term": "Spring 2026"}, [{"type": "schedule", "rows": [{"week": 1, "date": "1/6"}]}]),
        2: _part_reply({}, [{"type": "schedule", "rows": [{"week": 1, "date": "1/8"}, {"week": 2, "date": "1/13"}]}]),
    }
    monkeypatch.setattr("chalk.pdf_import.ai_reader.PART_CHARS", 40)
    monkeypatch.setattr(
        "chalk.pdf_import.ai_reader.complete",
        lambda prompt, system="", max_tokens=2000, on_text=None: replies[1 if "part 1 of 2" in prompt else 2],
    )

    blocks = blocks_from_reply(ask_ai_to_read([Paragraph("x" * 30), Paragraph("y" * 30)]))

    [schedule] = [block for block in blocks if isinstance(block, Table)]
    assert [row[0] for row in schedule.rows[1:]] == [("Week 1 (1/6)",), ("Week 1 (1/8)",), ("Week 2 (1/13)",)]
