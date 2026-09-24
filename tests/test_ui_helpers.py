"""Unit tests for the UI's Streamlit-free helpers (upload handling, table
row builders, argv parsing) and the term-suggestion used by Rollover."""

from pathlib import Path

import pytest

from chalk.calendar_data import suggest_target_term
from chalk.pipeline import preview_rollover
from tests.fixtures import docx_builder, md_builder
from tests.sample_course import build_sample_course_data
from ui import tables
from ui.project_picker import project_from_argv
from ui.upload_view import extract_upload, save_upload

# ---- argv -----------------------------------------------------------------------------


def test_project_from_argv():
    assert project_from_argv(["--project", "C:/courses/IS-6640"]) == Path("C:/courses/IS-6640")
    assert project_from_argv(["--unrelated", "x"]) is None
    assert project_from_argv([]) is None


# ---- upload ---------------------------------------------------------------------------


def test_save_upload_keeps_only_the_base_filename(tmp_path):
    path = save_upload("../../evil/syllabus.md", b"content")
    assert path.name == "syllabus.md"
    assert path.read_bytes() == b"content"
    assert "evil" not in path.parts


def test_extract_upload_success_is_pending_and_acknowledged_when_consistent(tmp_project, tmp_path):
    outcome = extract_upload(tmp_project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    assert outcome.pending.acknowledged
    assert outcome.table_choice is None and outcome.error is None


def test_extract_upload_failed_consistency_is_pending_but_unacknowledged(tmp_project, tmp_path):
    outcome = extract_upload(tmp_project, docx_builder.build_syllabus_with_term_mismatch(tmp_path / "b.docx"))
    assert not outcome.pending.acknowledged


def test_extract_upload_with_several_tables_asks_for_a_choice(tmp_project, tmp_path):
    upload = md_builder.build_syllabus_with_multiple_candidate_tables(tmp_path / "two.md")
    outcome = extract_upload(tmp_project, upload)
    assert outcome.table_choice.upload_path == upload
    assert len(outcome.table_choice.candidates) == 2


def test_extract_upload_with_no_schedule_table_is_an_error(tmp_project, tmp_path):
    outcome = extract_upload(tmp_project, md_builder.build_syllabus_with_no_schedule_table(tmp_path / "n.md"))
    assert outcome.error.startswith("No schedule table found.")


def test_extract_upload_protected_file_is_an_error(tmp_project, tmp_path):
    outcome = extract_upload(tmp_project, docx_builder.build_password_protected_docx(tmp_path / "p.docx"))
    assert "This Word file is protected" in outcome.error


# ---- table rows -----------------------------------------------------------------------


def test_week_rows_in_date_order_with_breaks():
    rows = tables.week_rows(build_sample_course_data())
    assert rows[0] == {
        "Week": "1",
        "Date": "Aug 24 (8/24)",
        "Topics": "Topic 1A; Topic 1B",
        "Assignments": "Lab 1 Due",
        "Notes": "Video Quizzes are Taken After Reading Each Chapter",
    }
    assert rows[7]["Week"] == "Break"
    assert rows[7]["Date"] == "Oct 10 (10/10) – Oct 18 (10/18)"
    assert rows[7]["Topics"] == "Fall Break"


def test_assessment_and_university_date_rows():
    course_data = build_sample_course_data()
    assert tables.assessment_rows(course_data)[1] == {"Assessment": "Labs", "Weight": "25%"}
    assert tables.university_date_rows(course_data) == [
        {"Event": "Classes begin", "Date": "Aug 24 (8/24)"},
        {"Event": "Fall Break", "Date": "Oct 10 (10/10) – Oct 18 (10/18)"},
    ]


def test_preview_rows_mark_flags_and_new_weeks(tmp_project):
    plan = preview_rollover(
        tmp_project, build_sample_course_data(), "Fall 2027", target_duration_weeks=11, llm_generate_topics=False
    )
    rows = {row["Week"]: row for row in tables.preview_rows(plan.preview)}
    assert rows["Week 1"] == {"Week": "Week 1", "Current": "Aug 24 (8/24)", "New": "Aug 23 (8/23)", "Check": "✓"}
    assert rows["Week 11"]["Current"] == "(new week)"
    assert rows["Week 8"]["Check"].startswith("⚠ Fall Break 2027 is Oct 9–17")
    assert rows["Fall Break"]["New"] == "Oct 9 (10/9)"


def test_regular_week_count_ignores_breaks():
    assert tables.regular_week_count(build_sample_course_data()) == 10


# ---- term suggestion --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        ("Fall 2026", "Fall 2027"),
        ("Summer 2027", "Fall 2027"),  # no Summer 2028 listed -> next term after it
        ("Fall 2027", None),  # last term, no next-year match
        ("Winter Session", None),
    ],
)
def test_suggest_target_term(current, expected):
    terms = ["Fall 2026", "Spring 2027", "Summer 2027", "Fall 2027"]
    assert suggest_target_term(current, terms) == expected


def test_suggestion_works_on_the_real_bundled_calendar(tmp_project):
    import json

    terms = [t["term"] for t in json.loads(tmp_project.calendars_json.read_text(encoding="utf-8"))["terms"]]
    assert suggest_target_term("Fall 2026", terms) == "Fall 2027"
