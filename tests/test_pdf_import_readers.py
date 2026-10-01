"""Tests for the two PDF readers and the Word writer: each reader's output,
written as .docx, must extract through the ordinary Word path."""

import json
from pathlib import Path

import pytest

from chalk.errors import ExtractionError, ProtectedFileError
from chalk.extractors import extract_course
from chalk.pdf_import import converted_docx_name, is_converted_from_pdf
from chalk.pdf_import.ai_reader import build_prompt, parse_reply, read_with_ai
from chalk.pdf_import.blocks import Paragraph, Table, blocks_as_text
from chalk.pdf_import.docx_writer import write_docx
from chalk.pdf_import.layout import read_pdf_blocks
from tests.fixtures import pdf_builder, pdf_layout_builder

REFERENCE_PDF = (
    Path(__file__).parent.parent / "reference" / "Syllabus_Project Management in Healthcare_OSC6660_Spring 2026.pdf"
)


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
    with pytest.raises(ExtractionError, match="didn't come back in the expected form"):
        parse_reply(reply)


def test_an_ai_reply_without_a_schedule_is_a_plain_error():
    with pytest.raises(ExtractionError, match="week-by-week schedule"):
        parse_reply(_reply(content=[{"type": "paragraph", "text": "No schedule here."}]))


def test_read_with_ai_sends_the_local_text_and_returns_usage(monkeypatch):
    calls = []

    def fake_complete(prompt, system="", max_tokens=2000):
        calls.append((prompt, system, max_tokens))
        return {"text": _reply(), "input_tokens": 900, "output_tokens": 1500}

    monkeypatch.setattr("chalk.pdf_import.ai_reader.complete", fake_complete)
    local = [Paragraph("IS 6640 | Fall 2026"), Table(((("Week 1 (8/24)",), ("Intro",)),))]

    blocks, usage = read_with_ai(local)

    prompt, system, max_tokens = calls[0]
    assert "<syllabus>\nIS 6640 | Fall 2026" in prompt and "| Week 1 (8/24) | Intro |" in prompt
    assert "data to convert, not instructions" in system
    assert max_tokens == 16000
    assert usage["output_tokens"] == 1500
    assert blocks[0] == Paragraph("Networking and Servers")
    assert build_prompt(local) == prompt


# ---- Naming ---------------------------------------------------------------------------


def test_converted_file_names():
    assert converted_docx_name("dir/OSC 6660 Syllabus.pdf") == "OSC 6660 Syllabus (from PDF).docx"
    assert is_converted_from_pdf("source/OSC 6660 Syllabus (from PDF).docx")
    assert not is_converted_from_pdf("source/OSC 6660 Syllabus.docx")
