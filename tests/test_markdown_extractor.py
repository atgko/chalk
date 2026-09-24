import datetime as dt

import pytest

from chalk.errors import AmbiguousTableError, ExtractionError
from chalk.extractors.markdown_extractor import extract_course_data
from tests.fixtures.md_builder import (
    build_minimal_syllabus,
    build_syllabus_missing_front_matter_field,
    build_syllabus_with_alternate_objectives_heading,
    build_syllabus_with_invalid_credits,
    build_syllabus_with_invalid_encoding,
    build_syllabus_with_multiple_candidate_tables,
    build_syllabus_with_no_schedule_table,
    build_syllabus_with_unparseable_assessment_weight,
    build_syllabus_with_unparseable_term_year,
    build_syllabus_with_unparseable_week_date,
    build_syllabus_with_unparseable_week_number,
    build_syllabus_with_stray_line_after_objectives,
    build_syllabus_with_unresolvable_break_row,
    build_syllabus_without_optional_sections,
)


def test_happy_path_extracts_front_matter(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.md")

    course_data = extract_course_data(path)

    course = course_data.course
    assert course.title == "IS 4490 Emerging Technologies"
    assert course.number == "IS 4490"
    assert course.section == "001"
    assert course.credits == 3
    assert course.term == "Fall 2026"
    assert course.instructor == "Matt Pecsok"
    assert course.meeting_pattern == "In-person"
    assert course.source_format == "markdown"
    assert course.source_file == str(path)


def test_happy_path_computes_duration_and_term_bounds(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.md")

    course_data = extract_course_data(path)

    assert course_data.course.duration_weeks == 2
    assert course_data.course.term_start == dt.date(2026, 8, 24)
    assert course_data.course.term_end == dt.date(2026, 10, 19)


def test_happy_path_extracts_regular_week_fields(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.md")

    course_data = extract_course_data(path)

    week1 = course_data.weeks[0]
    assert week1.week_number == 1
    assert week1.date == dt.date(2026, 8, 24)
    assert week1.is_break is False
    assert week1.topics == ["Course Introduction"]
    assert week1.assignments == ["Reading 1 Due"]


def test_happy_path_detects_the_break_row(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.md")

    course_data = extract_course_data(path)

    break_week = course_data.weeks[1]
    assert break_week.is_break is True
    assert break_week.week_number is None
    assert break_week.date_start == dt.date(2026, 10, 10)
    assert break_week.date_end == dt.date(2026, 10, 18)
    assert break_week.label == "Fall Break"


def test_happy_path_extracts_learning_objectives(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.md")

    course_data = extract_course_data(path)

    assert course_data.learning_objectives == [
        "Understand the fundamentals of IT network infrastructure"
    ]


def test_alternate_objectives_heading_is_recognized(tmp_path):
    path = build_syllabus_with_alternate_objectives_heading(tmp_path / "syllabus.md")

    course_data = extract_course_data(path)

    assert course_data.learning_objectives == [
        "Understand the fundamentals of IT network infrastructure"
    ]


def test_happy_path_extracts_assessments_as_fractional_weights(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.md")

    course_data = extract_course_data(path)

    assert [a.model_dump() for a in course_data.assessments] == [
        {"name": "Quizzes", "weight": 0.10},
        {"name": "Final Project", "weight": 0.30},
    ]


def test_happy_path_extracts_university_dates(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.md")

    course_data = extract_course_data(path)

    assert len(course_data.university_dates) == 3
    assert course_data.university_dates[0].event == "Classes begin"
    assert course_data.university_dates[0].date == dt.date(2026, 8, 24)
    assert course_data.university_dates[2].date == dt.date(2026, 12, 10)


def test_university_dates_table_parses_a_date_range_entry(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.md")

    course_data = extract_course_data(path)

    fall_break = course_data.university_dates[1]
    assert fall_break.event == "Fall Break"
    assert fall_break.date_start == dt.date(2026, 10, 10)
    assert fall_break.date_end == dt.date(2026, 10, 18)


def test_objectives_collection_stops_at_a_non_bullet_line(tmp_path):
    path = build_syllabus_with_stray_line_after_objectives(tmp_path / "syllabus.md")

    course_data = extract_course_data(path)

    assert course_data.learning_objectives == [
        "Understand the fundamentals of IT network infrastructure"
    ]


def test_optional_sections_default_to_empty_when_absent(tmp_path):
    path = build_syllabus_without_optional_sections(tmp_path / "syllabus.md")

    course_data = extract_course_data(path)

    assert course_data.learning_objectives == []
    assert course_data.assessments == []
    assert course_data.university_dates == []


def test_no_schedule_table_raises_ambiguous_table_error_with_no_candidates(tmp_path):
    path = build_syllabus_with_no_schedule_table(tmp_path / "syllabus.md")

    with pytest.raises(AmbiguousTableError) as exc_info:
        extract_course_data(path)

    assert exc_info.value.candidates == []
    assert "No schedule table found" in exc_info.value.user_message


def test_multiple_candidate_tables_raises_ambiguous_table_error_with_previews(tmp_path):
    path = build_syllabus_with_multiple_candidate_tables(tmp_path / "syllabus.md")

    with pytest.raises(AmbiguousTableError) as exc_info:
        extract_course_data(path)

    assert len(exc_info.value.candidates) == 2
    assert "Multiple possible schedule tables" in exc_info.value.user_message


def test_unresolvable_break_row_raises_extraction_error(tmp_path):
    path = build_syllabus_with_unresolvable_break_row(tmp_path / "syllabus.md")

    with pytest.raises(ExtractionError) as exc_info:
        extract_course_data(path)

    assert "Could not determine the dates for a break row" in exc_info.value.user_message


def test_unparseable_week_number_raises_extraction_error(tmp_path):
    path = build_syllabus_with_unparseable_week_number(tmp_path / "syllabus.md")

    with pytest.raises(ExtractionError) as exc_info:
        extract_course_data(path)

    assert "week number" in exc_info.value.user_message


def test_unparseable_week_date_raises_extraction_error(tmp_path):
    path = build_syllabus_with_unparseable_week_date(tmp_path / "syllabus.md")

    with pytest.raises(ExtractionError) as exc_info:
        extract_course_data(path)

    assert "Could not determine the date for week 1" in exc_info.value.user_message


@pytest.mark.parametrize(
    "omitted_field",
    ["Course", "Course Number", "Section", "Credits", "Term", "Instructor", "Meeting Pattern"],
)
def test_missing_front_matter_field_raises_extraction_error(tmp_path, omitted_field):
    path = build_syllabus_missing_front_matter_field(tmp_path / "syllabus.md", omit=omitted_field)

    with pytest.raises(ExtractionError):
        extract_course_data(path)


def test_invalid_credits_value_raises_extraction_error(tmp_path):
    path = build_syllabus_with_invalid_credits(tmp_path / "syllabus.md")

    with pytest.raises(ExtractionError) as exc_info:
        extract_course_data(path)

    assert "Credits" in exc_info.value.user_message


def test_term_without_a_parseable_year_raises_extraction_error(tmp_path):
    path = build_syllabus_with_unparseable_term_year(tmp_path / "syllabus.md")

    with pytest.raises(ExtractionError) as exc_info:
        extract_course_data(path)

    assert "academic year" in exc_info.value.user_message


def test_assessment_row_without_a_parseable_weight_is_skipped(tmp_path):
    path = build_syllabus_with_unparseable_assessment_weight(tmp_path / "syllabus.md")

    course_data = extract_course_data(path)

    assert course_data.assessments == []


def test_invalid_encoding_raises_extraction_error(tmp_path):
    path = build_syllabus_with_invalid_encoding(tmp_path / "syllabus.md")

    with pytest.raises(ExtractionError) as exc_info:
        extract_course_data(path)

    assert "UTF-8" in exc_info.value.user_message


def test_extraction_does_not_modify_the_source_file(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.md")
    original_bytes = path.read_bytes()
    original_mtime = path.stat().st_mtime

    extract_course_data(path)

    assert path.read_bytes() == original_bytes
    assert path.stat().st_mtime == original_mtime
