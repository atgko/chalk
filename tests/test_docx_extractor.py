import datetime as dt

import pytest

from chalk.errors import AmbiguousTableError, ExtractionError, ProtectedFileError
from chalk.extractors.docx_extractor import extract_course_data
from tests.fixtures.docx_builder import (
    build_minimal_syllabus,
    build_password_protected_docx,
    build_syllabus_missing_front_matter_field,
    build_syllabus_with_alternate_objectives_heading,
    build_syllabus_with_heading_after_objectives,
    build_syllabus_with_invalid_credits,
    build_syllabus_with_multiple_candidate_tables,
    build_syllabus_with_no_schedule_table,
    build_syllabus_with_unparseable_assessment_weight,
    build_syllabus_with_unparseable_term_year,
    build_syllabus_with_unresolvable_break_row,
    build_syllabus_without_university_dates_table,
)


def test_happy_path_extracts_front_matter(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.docx")

    course_data = extract_course_data(path)

    course = course_data.course
    assert course.title == "IS 6640 Networking and Servers"
    assert course.number == "IS 6640"
    assert course.section == "090"
    assert course.credits == 3
    assert course.term == "Fall 2026"
    assert course.instructor == "Dave Norwood"
    assert course.meeting_pattern == "Online async"
    assert course.source_format == "word"
    assert course.source_file == str(path)


def test_happy_path_computes_duration_and_term_bounds(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.docx")

    course_data = extract_course_data(path)

    # 2 regular weeks + 1 break row -> duration_weeks counts only the
    # non-break weeks.
    assert course_data.course.duration_weeks == 2
    assert course_data.course.term_start == dt.date(2026, 8, 24)
    assert course_data.course.term_end == dt.date(2026, 10, 19)


def test_happy_path_classifies_topics_assignments_and_notes(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.docx")

    course_data = extract_course_data(path)

    week1 = course_data.weeks[0]
    assert week1.week_number == 1
    assert week1.date == dt.date(2026, 8, 24)
    assert week1.is_break is False
    assert week1.topics == ["Course Introduction", "Network+ Mod 1", "Network+ Mod 2"]
    assert week1.assignments == ["Network+ Lab A Due"]
    assert week1.notes == "Video Quizzes are Taken After Reading Each Chapter"


def test_happy_path_detects_the_break_row(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.docx")

    course_data = extract_course_data(path)

    break_week = course_data.weeks[1]
    assert break_week.is_break is True
    assert break_week.week_number is None
    assert break_week.date_start == dt.date(2026, 10, 10)
    assert break_week.date_end == dt.date(2026, 10, 18)
    assert break_week.label == "Fall Break (10/10 - 10/18)"


def test_happy_path_extracts_assessments_as_fractional_weights(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.docx")

    course_data = extract_course_data(path)

    assert [a.model_dump() for a in course_data.assessments] == [
        {"name": "Video Quizzes", "weight": 0.05},
        {"name": "Labs", "weight": 0.25},
    ]


def test_happy_path_extracts_university_dates(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.docx")

    course_data = extract_course_data(path)

    assert len(course_data.university_dates) == 3
    assert course_data.university_dates[0].event == "Classes begin"
    assert course_data.university_dates[0].date == dt.date(2026, 8, 24)
    assert course_data.university_dates[2].date == dt.date(2026, 12, 10)


def test_university_dates_table_parses_a_date_range_entry(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.docx")

    course_data = extract_course_data(path)

    fall_break = course_data.university_dates[1]
    assert fall_break.event == "Fall Break"
    assert fall_break.date_start == dt.date(2026, 10, 10)
    assert fall_break.date_end == dt.date(2026, 10, 18)


def test_missing_university_dates_table_yields_empty_list(tmp_path):
    path = build_syllabus_without_university_dates_table(tmp_path / "syllabus.docx")

    course_data = extract_course_data(path)

    assert course_data.university_dates == []


def test_alternate_objectives_heading_is_recognized(tmp_path):
    path = build_syllabus_with_alternate_objectives_heading(tmp_path / "syllabus.docx")

    course_data = extract_course_data(path)

    assert course_data.learning_objectives == [
        "Understand the fundamentals of IT network infrastructure"
    ]


def test_objectives_collection_stops_at_the_next_heading(tmp_path):
    path = build_syllabus_with_heading_after_objectives(tmp_path / "syllabus.docx")

    course_data = extract_course_data(path)

    assert course_data.learning_objectives == [
        "Understand the fundamentals of IT network infrastructure"
    ]


def test_invalid_credits_value_raises_extraction_error(tmp_path):
    path = build_syllabus_with_invalid_credits(tmp_path / "syllabus.docx")

    with pytest.raises(ExtractionError) as exc_info:
        extract_course_data(path)

    assert "Credits" in exc_info.value.user_message


def test_term_without_a_parseable_year_raises_extraction_error(tmp_path):
    path = build_syllabus_with_unparseable_term_year(tmp_path / "syllabus.docx")

    with pytest.raises(ExtractionError) as exc_info:
        extract_course_data(path)

    assert "academic year" in exc_info.value.user_message


def test_assessment_row_without_a_parseable_weight_is_skipped(tmp_path):
    path = build_syllabus_with_unparseable_assessment_weight(tmp_path / "syllabus.docx")

    course_data = extract_course_data(path)

    assert course_data.assessments == []


def test_no_schedule_table_raises_ambiguous_table_error_with_no_candidates(tmp_path):
    path = build_syllabus_with_no_schedule_table(tmp_path / "syllabus.docx")

    with pytest.raises(AmbiguousTableError) as exc_info:
        extract_course_data(path)

    assert exc_info.value.candidates == []
    assert "No schedule table found" in exc_info.value.user_message


def test_multiple_candidate_tables_raises_ambiguous_table_error_with_previews(tmp_path):
    path = build_syllabus_with_multiple_candidate_tables(tmp_path / "syllabus.docx")

    with pytest.raises(AmbiguousTableError) as exc_info:
        extract_course_data(path)

    assert len(exc_info.value.candidates) == 2
    assert "Multiple possible schedule tables" in exc_info.value.user_message


def test_unresolvable_break_row_raises_extraction_error(tmp_path):
    path = build_syllabus_with_unresolvable_break_row(tmp_path / "syllabus.docx")

    with pytest.raises(ExtractionError) as exc_info:
        extract_course_data(path)

    assert "Could not determine the dates for the break row" in exc_info.value.user_message


@pytest.mark.parametrize(
    "omitted_field",
    ["course", "number", "section", "credits", "term", "instructor", "meeting_pattern"],
)
def test_missing_front_matter_field_raises_extraction_error(tmp_path, omitted_field):
    path = build_syllabus_missing_front_matter_field(
        tmp_path / "syllabus.docx", omit=omitted_field
    )

    with pytest.raises(ExtractionError):
        extract_course_data(path)


def test_password_protected_file_raises_protected_file_error(tmp_path):
    path = build_password_protected_docx(tmp_path / "protected.docx")

    with pytest.raises(ProtectedFileError) as exc_info:
        extract_course_data(path)

    assert "protected" in exc_info.value.user_message.lower()


def test_extraction_does_not_modify_the_source_file(tmp_path):
    path = build_minimal_syllabus(tmp_path / "syllabus.docx")
    original_bytes = path.read_bytes()
    original_mtime = path.stat().st_mtime

    extract_course_data(path)

    assert path.read_bytes() == original_bytes
    assert path.stat().st_mtime == original_mtime
