"""Tests for chalk.extractors' public dispatcher: format routing, the
"consistency check always runs" guarantee, and eval-log wiring for both
the automatic consistency_check event and the CLI/UI-triggered
consistency_check_override event."""

import pytest

from chalk.errors import ExtractionError
from chalk.extractors import extract_course, log_consistency_override
from chalk.metrics import read_events_by_type
from tests.fixtures.docx_builder import build_minimal_syllabus, build_syllabus_with_term_mismatch
from tests.fixtures.md_builder import build_minimal_syllabus as build_minimal_md_syllabus


def test_dispatches_docx_files_to_the_word_extractor(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.docx")

    course_data, consistency_result = extract_course(path)

    assert course_data.course.source_format == "word"
    assert consistency_result.passed is True


def test_dispatches_md_files_to_the_markdown_extractor(tmp_path):
    path = build_minimal_md_syllabus(tmp_path / "syllabus.md")

    course_data, consistency_result = extract_course(path)

    assert course_data.course.source_format == "markdown"
    assert consistency_result.passed is True


def test_unsupported_extension_raises_extraction_error(tmp_path):
    path = tmp_path / "syllabus.pdf"
    path.write_text("not a syllabus", encoding="utf-8")

    with pytest.raises(ExtractionError) as exc_info:
        extract_course(path)

    assert ".docx or .md" in exc_info.value.user_message


def test_consistency_check_always_runs_and_catches_the_named_bug(tmp_path):
    path = build_syllabus_with_term_mismatch(tmp_path / "syllabus.docx")

    _course_data, consistency_result = extract_course(path)

    assert consistency_result.passed is False
    assert "fall semester start" in consistency_result.detail


def test_no_eval_log_path_means_nothing_is_logged(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.docx")

    extract_course(path)  # eval_log_path omitted

    assert not (tmp_path / "eval-log.json").exists()


def test_passing_consistency_check_is_logged_automatically(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.docx")
    log_path = tmp_path / "eval-log.json"

    extract_course(path, eval_log_path=log_path)

    events = read_events_by_type(log_path, "consistency_check")
    assert len(events) == 1
    assert events[0]["passed"] is True
    assert events[0]["term"] == "Fall 2026"


def test_failing_consistency_check_is_logged_automatically(tmp_path):
    path = build_syllabus_with_term_mismatch(tmp_path / "syllabus.docx")
    log_path = tmp_path / "eval-log.json"

    extract_course(path, eval_log_path=log_path)

    events = read_events_by_type(log_path, "consistency_check")
    assert len(events) == 1
    assert events[0]["passed"] is False
    assert "fall semester start" in events[0]["detail"]


def test_override_is_logged_only_when_explicitly_called(tmp_path):
    path = build_syllabus_with_term_mismatch(tmp_path / "syllabus.docx")
    log_path = tmp_path / "eval-log.json"

    _course_data, consistency_result = extract_course(path, eval_log_path=log_path)
    assert read_events_by_type(log_path, "consistency_check_override") == []

    log_consistency_override(log_path, consistency_result)

    override_events = read_events_by_type(log_path, "consistency_check_override")
    assert len(override_events) == 1
    assert override_events[0]["term"] == "Spring 2026"
