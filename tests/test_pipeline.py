"""Tests for chalk.pipeline — the extract -> review-save -> rollover ->
export workflows, run against real synthetic syllabi inside a real
`init`-ed project directory."""

import datetime as dt

import pytest
from docx import Document

from chalk import metrics
from chalk.errors import ExtractionError, ProjectError, TermNotInCalendarError
from chalk.models import SourceMaterialRef
from chalk.pipeline import (
    confirm_rollover,
    export_outputs,
    extract_syllabus,
    preview_rollover,
    save_reviewed_course,
)
from chalk.project import load_course, save_course
from tests.fixtures import docx_builder, md_builder

# ---- extraction ------------------------------------------------------------------


def test_extract_copies_the_syllabus_into_source_and_records_a_relative_path(tmp_project, tmp_path):
    syllabus = docx_builder.build_minimal_syllabus(tmp_path / "IS-6640.docx")

    course_data, consistency = extract_syllabus(tmp_project, syllabus)

    assert consistency.passed
    assert course_data.course.source_file == "source/IS-6640.docx"
    assert (tmp_project.source_dir / "IS-6640.docx").exists()


def test_extract_does_not_save_course_json_before_review(tmp_project, tmp_path):
    syllabus = md_builder.build_minimal_syllabus(tmp_path / "syllabus.md")
    extract_syllabus(tmp_project, syllabus)
    assert load_course(tmp_project) is None


def test_extract_logs_extraction_and_consistency_events(tmp_project, tmp_path):
    syllabus = md_builder.build_minimal_syllabus(tmp_path / "syllabus.md")
    extract_syllabus(tmp_project, syllabus)

    extraction = metrics.read_events_by_type(tmp_project.eval_log, "extraction")
    assert extraction[-1]["filename"] == "syllabus.md"
    assert extraction[-1]["source_format"] == "markdown"
    assert metrics.read_events_by_type(tmp_project.eval_log, "consistency_check")[-1]["passed"]


def test_extract_reports_the_named_term_mismatch(tmp_project, tmp_path):
    syllabus = docx_builder.build_syllabus_with_term_mismatch(tmp_path / "bad.docx")
    _, consistency = extract_syllabus(tmp_project, syllabus)
    assert not consistency.passed
    assert "Spring 2026" in consistency.detail


def test_extract_logs_an_error_event_and_leaves_source_untouched_on_failure(tmp_project, tmp_path):
    syllabus = md_builder.build_syllabus_with_no_schedule_table(tmp_path / "broken.md")

    with pytest.raises(ExtractionError):
        extract_syllabus(tmp_project, syllabus)

    errors = metrics.read_events_by_type(tmp_project.eval_log, "extraction_error")
    assert errors[-1]["filename"] == "broken.md"
    assert errors[-1]["error_type"] == "AmbiguousTableError"
    assert not (tmp_project.source_dir / "broken.md").exists()


def test_reextraction_keeps_previously_indexed_source_materials(tmp_project, tmp_path):
    syllabus = md_builder.build_minimal_syllabus(tmp_path / "syllabus.md")
    first, _ = extract_syllabus(tmp_project, syllabus)
    ref = SourceMaterialRef(filename="ch3.pdf", added_at=dt.datetime(2026, 9, 17, tzinfo=dt.timezone.utc))
    save_course(tmp_project, first.model_copy(update={"source_materials": [ref]}))

    second, _ = extract_syllabus(tmp_project, syllabus)

    assert [m.filename for m in second.source_materials] == ["ch3.pdf"]


def test_save_reviewed_course_writes_course_json_and_brief(tmp_project, tmp_path):
    syllabus = md_builder.build_minimal_syllabus(tmp_path / "syllabus.md")
    course_data, _ = extract_syllabus(tmp_project, syllabus)

    written = save_reviewed_course(tmp_project, course_data)

    assert written == [tmp_project.course_json, tmp_project.course_brief]
    assert load_course(tmp_project) == course_data
    assert "# IS 4490 Emerging Technologies" in tmp_project.course_brief.read_text(encoding="utf-8")


# ---- rollover ----------------------------------------------------------------------


def _extracted_and_saved(tmp_project, tmp_path, builder, filename):
    syllabus = builder.build_minimal_syllabus(tmp_path / filename)
    course_data, _ = extract_syllabus(tmp_project, syllabus)
    save_reviewed_course(tmp_project, course_data)
    return course_data


def test_preview_writes_nothing(tmp_project, tmp_path):
    course_data = _extracted_and_saved(tmp_project, tmp_path, docx_builder, "s.docx")

    plan = preview_rollover(tmp_project, course_data, "Fall 2027", llm_generate_topics=False)

    assert plan.rolled_over.course.term == "Fall 2027"
    assert plan.files_to_write == [
        tmp_project.outputs_dir / "syllabus.docx",
        tmp_project.canvas_html,
        tmp_project.course_brief,
    ]
    assert not tmp_project.syllabus_output("word").exists()
    assert not tmp_project.canvas_html.exists()
    assert load_course(tmp_project).course.term == "Fall 2026"


def test_preview_requires_a_week1_date_for_terms_missing_from_the_calendar(tmp_project, tmp_path):
    course_data = _extracted_and_saved(tmp_project, tmp_path, md_builder, "s.md")

    with pytest.raises(TermNotInCalendarError) as exc_info:
        preview_rollover(tmp_project, course_data, "Fall 2099")
    assert "first day of classes" in exc_info.value.user_message

    plan = preview_rollover(
        tmp_project,
        course_data,
        "Fall 2099",
        manual_week1_date=dt.date(2099, 8, 24),
        llm_generate_topics=False,
    )
    assert plan.rolled_over.course.term_start == dt.date(2099, 8, 24)


def test_preview_flags_a_deliberate_duration_change_instead_of_blocking(tmp_project, tmp_path):
    course_data = _extracted_and_saved(tmp_project, tmp_path, md_builder, "s.md")
    lengthened = course_data.model_copy(
        update={"course": course_data.course.model_copy(update={"duration_weeks": 4})}
    )

    plan = preview_rollover(tmp_project, lengthened, "Fall 2027", llm_generate_topics=False)

    assert plan.rolled_over.course.duration_weeks == 4
    assert plan.preview.general_flags[0].startswith(
        "The course has 2 weeks in the schedule but duration_weeks says 4."
    )


def test_confirm_writes_every_planned_file_and_logs_a_rollover(tmp_project, tmp_path):
    course_data = _extracted_and_saved(tmp_project, tmp_path, docx_builder, "s.docx")
    plan = preview_rollover(tmp_project, course_data, "Fall 2027", llm_generate_topics=False)

    written = confirm_rollover(tmp_project, plan)

    assert written[:3] == plan.files_to_write
    assert written[3] == tmp_project.course_json
    rolled_doc = Document(str(tmp_project.syllabus_output("word")))
    assert "Week 1 (8/23)" in [cell.text for table in rolled_doc.tables for cell in table.columns[0].cells]
    assert "Fall 2027" in tmp_project.canvas_html.read_text(encoding="utf-8")
    assert "Fall 2027" in tmp_project.course_brief.read_text(encoding="utf-8")
    assert load_course(tmp_project).course.term == "Fall 2027"

    event = metrics.read_events_by_type(tmp_project.eval_log, "rollover")[-1]
    assert (event["source_term"], event["target_term"]) == ("Fall 2026", "Fall 2027")
    assert event["source_duration_weeks"] == event["target_duration_weeks"] == 2


def test_confirm_on_markdown_writes_syllabus_md_and_archives_prior_outputs(tmp_project, tmp_path):
    course_data = _extracted_and_saved(tmp_project, tmp_path, md_builder, "s.md")
    brief_before = tmp_project.course_brief.read_text(encoding="utf-8")

    confirm_rollover(
        tmp_project, preview_rollover(tmp_project, course_data, "Fall 2027", llm_generate_topics=False)
    )

    assert "Term: Fall 2027" in tmp_project.syllabus_output("markdown").read_text(encoding="utf-8")
    archived_briefs = list((tmp_project.outputs_dir / ".archive").glob("course-brief-*.md"))
    assert [p.read_text(encoding="utf-8") for p in archived_briefs] == [brief_before]


def test_confirm_reports_a_missing_original_syllabus(tmp_project, tmp_path):
    course_data = _extracted_and_saved(tmp_project, tmp_path, md_builder, "s.md")
    plan = preview_rollover(tmp_project, course_data, "Fall 2027", llm_generate_topics=False)
    (tmp_project.source_dir / "s.md").unlink()

    with pytest.raises(ProjectError, match="original syllabus"):
        confirm_rollover(tmp_project, plan)


def test_confirm_accepts_an_absolute_source_file_path(tmp_project, tmp_path):
    course_data = _extracted_and_saved(tmp_project, tmp_path, md_builder, "s.md")
    absolute = course_data.model_copy(
        update={
            "course": course_data.course.model_copy(
                update={"source_file": str(tmp_project.source_dir / "s.md")}
            )
        }
    )
    plan = preview_rollover(tmp_project, absolute, "Fall 2027", llm_generate_topics=False)

    confirm_rollover(tmp_project, plan)

    assert tmp_project.syllabus_output("markdown").exists()


# ---- export ------------------------------------------------------------------------


def test_export_writes_canvas_html_and_course_brief(tmp_project, tmp_path):
    course_data = _extracted_and_saved(tmp_project, tmp_path, md_builder, "s.md")

    written = export_outputs(tmp_project, course_data)

    assert written == [tmp_project.canvas_html, tmp_project.course_brief]
    assert tmp_project.canvas_html.read_text(encoding="utf-8").startswith("<!-- Generated by Chalk")
