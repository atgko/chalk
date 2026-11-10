"""The class time and location at rollover (Nov 9 UAT): changed wherever
the syllabus repeats them, not just where extraction read them."""

import datetime as dt

from docx import Document

from chalk.models import CourseInfo
from chalk.pipeline import (
    confirm_rollover,
    extract_syllabus,
    preview_rollover,
    save_reviewed_course,
)
from chalk.rollover.class_details import (
    TextChange,
    class_detail_changes,
    document_lines,
    other_time_mentions,
    replace_in_document,
    replace_in_lines,
    updated_course_details,
)
from tests.fixtures import md_builder


def _course(**updates) -> CourseInfo:
    base = CourseInfo(
        title="Networking",
        number="IS 6640",
        term="Fall 2026",
        term_start=dt.date(2026, 8, 24),
        term_end=dt.date(2026, 12, 10),
        duration_weeks=10,
        meeting_pattern="Tuesdays 5PM - 6PM",
        location="WEB L104",
        source_format="word",
        source_file="source/s.docx",
        extracted_at=dt.datetime(2026, 11, 9, tzinfo=dt.UTC),
    )
    return base.model_copy(update=updates)


# ---- What changes ----------------------------------------------------------------


def test_a_new_time_and_room_change_the_old_ones():
    changes, notes = class_detail_changes(_course(), "Wednesdays 6PM - 7PM", "CRCC 105")

    assert changes == [
        TextChange("Tuesdays 5PM - 6PM", "Wednesdays 6PM - 7PM", "class time"),
        TextChange("WEB L104", "CRCC 105", "location"),
    ]
    assert notes == []


def test_a_blank_location_becomes_tba_so_last_terms_room_isnt_kept():
    changes, _ = class_detail_changes(_course(), "Tuesdays 5PM - 6PM", "")

    assert changes == [TextChange("WEB L104", "TBA", "location")]
    assert updated_course_details(_course(), None, "")["location"] == "TBA"


def test_unchanged_or_unasked_details_change_nothing():
    assert class_detail_changes(_course(), "Tuesdays 5PM - 6PM", "WEB L104") == ([], [])
    assert class_detail_changes(_course(), None, None) == ([], [])
    assert updated_course_details(_course(), None, None) == {}


def test_details_the_syllabus_never_stated_get_a_note_instead():
    changes, notes = class_detail_changes(_course(meeting_pattern="", location=""), "Wed 6 pm", "CRCC 105")

    assert changes == []
    assert len(notes) == 2 and all("add" in note and "by hand" in note for note in notes)
    assert updated_course_details(_course(location=""), None, "")["location"] == ""


# ---- Word: every repeat, in any run, table, header, or footer -----------------------


def _document_with_repeats():
    document = Document()
    document.add_paragraph("Time: Tuesdays 5PM - 6PM")
    split = document.add_paragraph("Webinars are ")
    split.add_run("Tuesdays ").bold = True
    split.add_run("5PM - 6PM in WEB L104, every week.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Room"
    table.rows[0].cells[1].text = "WEB L104"
    document.sections[0].footer.paragraphs[0].text = "IS 6640 · Tuesdays 5PM - 6PM"
    return document


def test_every_repeat_in_a_word_document_is_changed_keeping_formatting():
    document = _document_with_repeats()
    changes = [
        TextChange("Tuesdays 5PM - 6PM", "Wednesdays 6PM - 7PM", "class time"),
        TextChange("WEB L104", "CRCC 105", "location"),
    ]

    assert replace_in_document(document, changes) == 5

    lines = document_lines(document)
    assert "Time: Wednesdays 6PM - 7PM" in lines
    assert "Webinars are Wednesdays 6PM - 7PM in CRCC 105, every week." in lines
    assert "CRCC 105" in lines
    assert "IS 6640 · Wednesdays 6PM - 7PM" in lines
    split = document.paragraphs[1]
    assert split.runs[1].bold and split.runs[1].text == "Wednesdays 6PM - 7PM"


def test_a_replacement_containing_the_old_text_doesnt_loop():
    document = Document()
    document.add_paragraph("Room: WEB")

    assert replace_in_document(document, [TextChange("WEB", "WEB L104", "location")]) == 1
    assert document.paragraphs[0].text == "Room: WEB L104"


def test_markdown_lines_are_changed_too():
    lines = ["**Time:** Tuesdays 5PM - 6PM", "Meet Tuesdays 5PM - 6PM."]

    assert replace_in_lines(lines, [TextChange("Tuesdays 5PM - 6PM", "Wed 6 pm", "class time")]) == [
        "**Time:** Wed 6 pm",
        "Meet Wed 6 pm.",
    ]


# ---- Other mentions to check by hand ------------------------------------------------


def test_other_day_and_time_lines_are_listed_but_not_office_hours_or_the_known_time():
    lines = [
        "Time: Tuesdays 5PM - 6PM",
        "Labs are due Sundays at 11:59 pm",
        "Office hours: Mondays 2-3 pm",
        "Week 1 (8/24) Course introduction",
        "Labs are due Sundays at 11:59 pm",
    ]

    assert other_time_mentions(lines, [], _course()) == ["Labs are due Sundays at 11:59 pm"]


# ---- Through the pipeline ------------------------------------------------------


def test_rollover_changes_the_time_and_room_everywhere_in_the_written_syllabus(tmp_project, tmp_path):
    syllabus = tmp_path / "s.docx"
    document = Document()
    for line in (
        "Course: IS 6640 Networking and Servers",
        "Term: Fall 2026",
        "Meeting Pattern: Tuesdays 5PM - 6PM",
        "Location: WEB L104",
        "We meet Tuesdays 5PM - 6PM in WEB L104.",
        "Quizzes close Fridays at 11:59 pm.",
    ):
        document.add_paragraph(line)
    table = document.add_table(rows=3, cols=2)
    for row, (label, text) in zip(table.rows, [("Week", "Topics"), ("Week 1 (8/24)", "Intro"), ("Week 2 (8/31)", "Mod 2")], strict=True):
        row.cells[0].text, row.cells[1].text = label, text
    document.save(str(syllabus))
    course_data, _ = extract_syllabus(tmp_project, syllabus)
    save_reviewed_course(tmp_project, course_data)
    assert course_data.course.location == "WEB L104"

    plan = preview_rollover(
        tmp_project, course_data, "Spring 2027", llm_generate_topics=False, class_time="Wed 6-8:45 pm", location=""
    )

    flags = plan.preview.general_flags
    assert 'The class time "Tuesdays 5PM - 6PM" becomes "Wed 6-8:45 pm" everywhere it appears in the syllabus.' in flags
    assert 'The location "WEB L104" becomes "TBA" everywhere it appears in the syllabus.' in flags
    assert any('"Quizzes close Fridays at 11:59 pm."' in flag for flag in flags)
    assert (plan.rolled_over.course.meeting_pattern, plan.rolled_over.course.location) == ("Wed 6-8:45 pm", "TBA")

    confirm_rollover(tmp_project, plan)

    text = "\n".join(document_lines(Document(str(tmp_project.syllabus_output("word")))))
    assert "We meet Wed 6-8:45 pm in TBA." in text
    assert "Tuesdays 5PM - 6PM" not in text and "WEB L104" not in text


def test_markdown_rollover_changes_the_time_too(tmp_project, tmp_path):
    syllabus = md_builder.build_minimal_syllabus(tmp_path / "s.md")
    course_data, _ = extract_syllabus(tmp_project, syllabus)
    save_reviewed_course(tmp_project, course_data)
    old_time = course_data.course.meeting_pattern
    assert old_time

    plan = preview_rollover(tmp_project, course_data, "Fall 2027", llm_generate_topics=False, class_time="Thu 1 pm")
    confirm_rollover(tmp_project, plan)

    written = tmp_project.syllabus_output("markdown").read_text(encoding="utf-8")
    assert "Thu 1 pm" in written and old_time not in written
