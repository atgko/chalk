"""Tests for chalk.rollover.markdown_rollover.

Mirrors test_docx_rollover.py's approach: new_course_data is built by
hand from the extracted source data, isolating "does the writer apply a
given CourseData correctly" from "does roll_over_course compute the right
dates" (covered separately in test_rollover_preview.py).
"""

import datetime as dt

from chalk.extractors.markdown_extractor import extract_course_data
from chalk.metrics import read_events_by_type
from chalk.rollover.markdown_rollover import write_rolled_over_markdown
from tests.fixtures.md_builder import build_minimal_syllabus, build_syllabus_without_optional_sections


def _rolled_over_copy(
    course_data,
    *,
    week_dates: dict,
    break_dates=(dt.date(2027, 10, 9), dt.date(2027, 10, 17)),
    term: str = "Fall 2027",
):
    # break_dates defaults to a Fall-2027-consistent range because
    # _render_schedule_table sorts weeks chronologically before writing:
    # leaving the break at its original (2026) dates while week 1 moves
    # to 2027 would create a genuinely inconsistent intermediate state
    # (a "2026" break sorting before a "2027" week) that a real rollover
    # never produces, since roll_over_course() always moves every date
    # together.
    new_weeks = []
    for week in course_data.weeks:
        if week.is_break:
            if break_dates is not None:
                new_start, new_end = break_dates
                new_weeks.append(
                    week.model_copy(update={"date_start": new_start, "date_end": new_end})
                )
            else:
                new_weeks.append(week)
            continue

        new_date = week_dates.get(week.week_number)
        if new_date is None:
            new_weeks.append(week)
            continue
        new_weeks.append(week.model_copy(update={"date": new_date}))

    new_course_info = course_data.course.model_copy(update={"term": term})
    return course_data.model_copy(update={"course": new_course_info, "weeks": new_weeks})


def test_updates_week_dates_in_the_regenerated_table(tmp_path):
    source_path = build_minimal_syllabus(tmp_path / "syllabus.md")
    course_data = extract_course_data(source_path)

    new_course_data = _rolled_over_copy(
        course_data,
        week_dates={1: dt.date(2027, 8, 23), 2: dt.date(2027, 10, 18)},
        break_dates=(dt.date(2027, 10, 9), dt.date(2027, 10, 17)),
    )

    output_path = tmp_path / "outputs" / "syllabus.md"
    write_rolled_over_markdown(source_path, new_course_data, output_path)

    rolled_data = extract_course_data(output_path)
    assert next(w for w in rolled_data.weeks if w.week_number == 1).date == dt.date(2027, 8, 23)
    week2 = next(week for week in rolled_data.weeks if week.week_number == 2)
    assert week2.date == dt.date(2027, 10, 18)
    break_week = next(week for week in rolled_data.weeks if week.is_break)
    assert break_week.date_start == dt.date(2027, 10, 9)
    assert break_week.date_end == dt.date(2027, 10, 17)


def test_term_label_is_updated_so_reextraction_uses_the_right_year(tmp_path):
    source_path = build_minimal_syllabus(tmp_path / "syllabus.md")
    course_data = extract_course_data(source_path)

    new_course_data = _rolled_over_copy(
        course_data, week_dates={1: dt.date(2027, 8, 23)}, term="Fall 2027"
    )

    output_path = tmp_path / "outputs" / "syllabus.md"
    write_rolled_over_markdown(source_path, new_course_data, output_path)

    rolled_data = extract_course_data(output_path)
    assert rolled_data.course.term == "Fall 2027"
    assert next(w for w in rolled_data.weeks if w.week_number == 1).date == dt.date(2027, 8, 23)


def test_topics_and_major_work_are_preserved(tmp_path):
    source_path = build_minimal_syllabus(tmp_path / "syllabus.md")
    course_data = extract_course_data(source_path)

    new_course_data = _rolled_over_copy(course_data, week_dates={1: dt.date(2027, 8, 23)})

    output_path = tmp_path / "outputs" / "syllabus.md"
    write_rolled_over_markdown(source_path, new_course_data, output_path)

    week1 = next(w for w in extract_course_data(output_path).weeks if w.week_number == 1)
    assert week1.topics == ["Course Introduction"]
    assert week1.assignments == ["Reading 1 Due"]


def test_other_content_in_the_file_is_left_untouched(tmp_path):
    source_path = build_minimal_syllabus(tmp_path / "syllabus.md")
    course_data = extract_course_data(source_path)

    new_course_data = _rolled_over_copy(course_data, week_dates={1: dt.date(2027, 8, 23)})

    output_path = tmp_path / "outputs" / "syllabus.md"
    write_rolled_over_markdown(source_path, new_course_data, output_path)

    rolled_data = extract_course_data(output_path)
    # Assessments table and objectives live outside the schedule table and
    # aren't touched by rollover at all.
    assert rolled_data.learning_objectives == course_data.learning_objectives
    assert [a.model_dump() for a in rolled_data.assessments] == [
        a.model_dump() for a in course_data.assessments
    ]


def test_university_dates_table_is_updated(tmp_path):
    source_path = build_minimal_syllabus(tmp_path / "syllabus.md")
    course_data = extract_course_data(source_path)

    new_course_data = _rolled_over_copy(course_data, week_dates={1: dt.date(2027, 8, 23)})
    new_university_dates = [
        entry.model_copy(update={"date": dt.date(2027, 8, 23)})
        if entry.event == "Classes begin"
        else entry
        for entry in new_course_data.university_dates
    ]
    new_course_data = new_course_data.model_copy(update={"university_dates": new_university_dates})

    output_path = tmp_path / "outputs" / "syllabus.md"
    write_rolled_over_markdown(source_path, new_course_data, output_path)

    rolled_data = extract_course_data(output_path)
    classes_begin = next(d for d in rolled_data.university_dates if d.event == "Classes begin")
    assert classes_begin.date == dt.date(2027, 8, 23)


def test_university_date_row_with_no_matching_event_is_left_alone(tmp_path):
    source_path = build_minimal_syllabus(tmp_path / "syllabus.md")
    course_data = extract_course_data(source_path)

    new_course_data = _rolled_over_copy(course_data, week_dates={1: dt.date(2027, 8, 23)})
    new_course_data = new_course_data.model_copy(
        update={
            "university_dates": [
                entry for entry in new_course_data.university_dates if entry.event != "Classes begin"
            ]
        }
    )

    output_path = tmp_path / "outputs" / "syllabus.md"
    write_rolled_over_markdown(source_path, new_course_data, output_path)

    rolled_data = extract_course_data(output_path)
    classes_begin = next(d for d in rolled_data.university_dates if d.event == "Classes begin")
    assert classes_begin.date == dt.date(2026, 8, 24)  # untouched, stale but not crashed


def test_no_university_dates_table_does_not_crash(tmp_path):
    source_path = build_syllabus_without_optional_sections(tmp_path / "syllabus.md")
    course_data = extract_course_data(source_path)

    new_course_data = _rolled_over_copy(course_data, week_dates={1: dt.date(2027, 8, 23)})

    output_path = tmp_path / "outputs" / "syllabus.md"
    write_rolled_over_markdown(source_path, new_course_data, output_path)

    rolled_data = extract_course_data(output_path)
    assert rolled_data.university_dates == []
    week1 = next(w for w in rolled_data.weeks if w.week_number == 1)
    assert week1.date == dt.date(2027, 8, 23)


def test_original_source_file_is_never_modified(tmp_path):
    source_path = build_minimal_syllabus(tmp_path / "syllabus.md")
    original_bytes = source_path.read_bytes()
    course_data = extract_course_data(source_path)

    new_course_data = _rolled_over_copy(course_data, week_dates={1: dt.date(2027, 8, 23)})
    write_rolled_over_markdown(source_path, new_course_data, tmp_path / "outputs" / "syllabus.md")

    assert source_path.read_bytes() == original_bytes


def test_existing_output_is_archived_before_being_overwritten(tmp_path):
    source_path = build_minimal_syllabus(tmp_path / "syllabus.md")
    course_data = extract_course_data(source_path)
    new_course_data = _rolled_over_copy(course_data, week_dates={1: dt.date(2027, 8, 23)})

    output_path = tmp_path / "outputs" / "syllabus.md"
    output_path.parent.mkdir(parents=True)
    output_path.write_text("stale previous version", encoding="utf-8")

    write_rolled_over_markdown(source_path, new_course_data, output_path)

    archive_dir = output_path.parent / ".archive"
    archived_files = list(archive_dir.iterdir())
    assert len(archived_files) == 1
    assert archived_files[0].read_text(encoding="utf-8") == "stale previous version"

    rolled_data = extract_course_data(output_path)
    assert next(w for w in rolled_data.weeks if w.week_number == 1).date == dt.date(2027, 8, 23)


def test_archive_event_is_logged_when_eval_log_path_given(tmp_path):
    source_path = build_minimal_syllabus(tmp_path / "syllabus.md")
    course_data = extract_course_data(source_path)
    new_course_data = _rolled_over_copy(course_data, week_dates={1: dt.date(2027, 8, 23)})

    output_path = tmp_path / "outputs" / "syllabus.md"
    output_path.parent.mkdir(parents=True)
    output_path.write_text("stale", encoding="utf-8")
    log_path = tmp_path / "eval-log.json"

    write_rolled_over_markdown(source_path, new_course_data, output_path, eval_log_path=log_path)

    assert len(read_events_by_type(log_path, "archive")) == 1


def test_multiple_topics_are_joined_rather_than_dropped(tmp_path):
    source_path = build_minimal_syllabus(tmp_path / "syllabus.md")
    course_data = extract_course_data(source_path)

    weeks = [
        week.model_copy(update={"topics": ["Topic A", "Topic B"]}) if week.week_number == 1 else week
        for week in course_data.weeks
    ]
    course_data = course_data.model_copy(update={"weeks": weeks})
    new_course_data = _rolled_over_copy(course_data, week_dates={1: dt.date(2027, 8, 23)})

    output_path = tmp_path / "outputs" / "syllabus.md"
    write_rolled_over_markdown(source_path, new_course_data, output_path)

    week1 = next(w for w in extract_course_data(output_path).weeks if w.week_number == 1)
    assert week1.topics == ["Topic A; Topic B"]
