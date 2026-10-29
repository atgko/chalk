"""A class that meets more than once a week, with one schedule row per
class meeting ("Week 2 (1/13)", "Week 2 (1/15)"). An undergraduate
syllabus laid out this way was read as 29 weeks (sponsor meeting,
Oct 28): each row stays its own entry, numbered by `Week.meeting`, and
the course counts weeks, not rows."""

import datetime as dt

from docx import Document

from chalk.extractors.docx_extractor import extract_course_data
from chalk.extractors.meetings import number_meetings, week_count, with_meetings
from chalk.generation.engine import _find_week
from chalk.models import Week
from chalk.rollover.docx_rollover import write_rolled_over_docx
from chalk.rollover.meeting_days import schedule_meeting_days
from chalk.rollover.preview import roll_over_course
from tests.fixtures.docx_builder import build_minimal_syllabus, build_twice_weekly_syllabus

CALENDARS = {
    "terms": [
        {"term": "Spring 2026", "start": "2026-01-05", "end": "2026-04-28", "no_class_dates": []},
        {
            "term": "Fall 2026",
            "start": "2026-08-24",
            "end": "2026-12-10",
            # On Wednesday of Week 1: only that week's second meeting.
            "no_class_dates": [{"label": "Founders Day", "date": "2026-08-26"}],
        },
    ]
}


def _course(tmp_path, weeks: int = 3):
    return extract_course_data(build_twice_weekly_syllabus(tmp_path / "twice.docx", weeks=weeks))


def _regular(course_data):
    return [week for week in course_data.weeks if not week.is_break]


def _week(number, meeting, date):
    return Week(week_number=number, meeting=meeting, date=date, label=f"Week {number}")


# ---- Extraction -----------------------------------------------------------------------


def test_each_class_meeting_is_its_own_row_and_the_course_counts_weeks(tmp_path):
    course_data = _course(tmp_path)

    rows = _regular(course_data)
    assert [(w.week_number, w.meeting) for w in rows] == [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 2)]
    assert [w.date for w in rows[:2]] == [dt.date(2026, 1, 6), dt.date(2026, 1, 8)]
    assert [w.topics for w in rows[:2]] == [["Topic 1a"], ["Topic 1b"]]
    assert course_data.course.duration_weeks == 3


def test_a_once_a_week_schedule_has_no_meeting_numbers(tmp_path):
    course_data = extract_course_data(build_minimal_syllabus(tmp_path / "weekly.docx"))

    assert all(week.meeting is None for week in course_data.weeks)
    assert course_data.course.duration_weeks == 2


def test_number_meetings_counts_within_each_week_and_skips_breaks():
    assert number_meetings([1, 1, 2, None, 2, 3]) == [1, 2, 1, None, 2, 1]
    assert number_meetings([1, 2, None, 3]) == [None, None, None, None]


def test_week_count_counts_distinct_weeks():
    weeks = [_week(1, 1, dt.date(2026, 1, 6)), _week(1, 2, dt.date(2026, 1, 8)), _week(2, 1, dt.date(2026, 1, 13))]

    assert week_count(weeks) == 2


# ---- Rollover ------------------------------------------------------------------------


def test_rollover_keeps_each_meetings_spacing_within_its_week(tmp_path):
    new_course, preview = roll_over_course(_course(tmp_path), target_term="Fall 2026", calendars=CALENDARS)

    dates = [w.date for w in _regular(new_course)]
    assert dates == [
        dt.date(2026, 8, 24),
        dt.date(2026, 8, 26),
        dt.date(2026, 8, 31),
        dt.date(2026, 9, 2),
        dt.date(2026, 9, 7),
        dt.date(2026, 9, 9),
    ]
    assert new_course.course.duration_weeks == 3
    assert preview.source_duration_weeks == preview.target_duration_weeks == 3
    assert not preview.general_flags


def test_shortening_drops_every_meeting_of_the_dropped_weeks(tmp_path):
    new_course, _ = roll_over_course(
        _course(tmp_path), target_term="Fall 2026", calendars=CALENDARS, target_duration_weeks=2
    )

    assert [(w.week_number, w.meeting) for w in _regular(new_course)] == [(1, 1), (1, 2), (2, 1), (2, 2)]


def test_lengthening_adds_one_row_per_added_week(tmp_path):
    new_course, _ = roll_over_course(
        _course(tmp_path),
        target_term="Fall 2026",
        calendars=CALENDARS,
        target_duration_weeks=4,
        llm_generate_topics=False,
    )

    added = _regular(new_course)[6:]
    assert [(w.week_number, w.meeting, w.date) for w in added] == [(4, None, dt.date(2026, 9, 14))]


def test_a_holiday_is_flagged_only_on_the_meeting_it_falls_on(tmp_path):
    _, preview = roll_over_course(_course(tmp_path), target_term="Fall 2026", calendars=CALENDARS)

    flagged = [(c.week_number, c.meeting) for c in preview.week_changes if c.flags]
    assert flagged == [(1, 2)]


def test_the_word_rollover_rewrites_each_meeting_row_with_its_own_date(tmp_path):
    source = build_twice_weekly_syllabus(tmp_path / "twice.docx")
    new_course, _ = roll_over_course(extract_course_data(source), target_term="Fall 2026", calendars=CALENDARS)
    output = tmp_path / "out.docx"

    write_rolled_over_docx(source, new_course, output)

    schedule = Document(str(output)).tables[0]
    assert [(row.cells[0].text, row.cells[1].text) for row in schedule.rows[1:3]] == [
        ("Week 1 (8/24)", "Topic 1a"),
        ("Week 1 (8/26)", "Topic 1b"),
    ]
    reread = extract_course_data(output)
    assert reread.course.duration_weeks == 3
    assert [w.date for w in _regular(reread)] == [w.date for w in _regular(new_course)]


# ---- Generation ----------------------------------------------------------------------


def test_generating_for_a_week_covers_all_of_its_meetings(tmp_path):
    week = _find_week(_course(tmp_path), 2)

    assert week.topics == ["Topic 2a", "Topic 2b"]


# ---- Dating meetings on the days picked for the new term ---------------------------


def _dates(new_course):
    return [w.date for w in _regular(new_course)]


def test_meetings_are_dated_on_the_days_picked_for_the_new_term(tmp_path):
    new_course, preview = roll_over_course(
        _course(tmp_path), target_term="Fall 2026", calendars=CALENDARS, meeting_days=(1, 3)
    )

    assert _dates(new_course) == [
        dt.date(2026, 8, 25),
        dt.date(2026, 8, 27),
        dt.date(2026, 9, 1),
        dt.date(2026, 9, 3),
        dt.date(2026, 9, 8),
        dt.date(2026, 9, 10),
    ]
    assert [w.label for w in _regular(new_course)[:2]] == ["Week 1 (8/25)", "Week 1 (8/27)"]
    # Founders Day (Wed 8/26) isn't a class day any more.
    assert not any(change.flags for change in preview.week_changes)


def test_meetings_can_move_to_other_days(tmp_path):
    new_course, _ = roll_over_course(
        _course(tmp_path), target_term="Fall 2026", calendars=CALENDARS, meeting_days=(0, 4)
    )

    assert _dates(new_course)[:4] == [
        dt.date(2026, 8, 24),
        dt.date(2026, 8, 28),
        dt.date(2026, 8, 31),
        dt.date(2026, 9, 4),
    ]


def test_a_course_starting_midweek_meets_first_on_its_first_day(tmp_path):
    new_course, _ = roll_over_course(
        _course(tmp_path),
        target_term="Fall 2026",
        calendars=CALENDARS,
        manual_week1_date=dt.date(2026, 8, 26),  # a Wednesday
        meeting_days=(0, 2),
    )

    assert _dates(new_course)[:4] == [
        dt.date(2026, 8, 26),
        dt.date(2026, 8, 31),
        dt.date(2026, 9, 2),
        dt.date(2026, 9, 7),
    ]


def test_a_week_with_only_its_thursday_row_moves_to_the_second_day(tmp_path):
    course = _course(tmp_path)
    without_week2_tuesday = [w for w in course.weeks if (w.week_number, w.meeting) != (2, 1)]
    course = course.model_copy(update={"weeks": with_meetings(without_week2_tuesday)})

    new_course, _ = roll_over_course(course, target_term="Fall 2026", calendars=CALENDARS, meeting_days=(0, 2))

    week2 = [w for w in _regular(new_course) if w.week_number == 2]
    assert [(w.topics, w.date) for w in week2] == [(["Topic 2b"], dt.date(2026, 9, 2))]


def test_picking_a_different_number_of_days_keeps_the_spacing_and_says_so(tmp_path):
    new_course, preview = roll_over_course(
        _course(tmp_path), target_term="Fall 2026", calendars=CALENDARS, meeting_days=(0, 2, 4)
    )

    assert _dates(new_course)[:2] == [dt.date(2026, 8, 24), dt.date(2026, 8, 26)]
    assert any("2 class meetings a week" in flag for flag in preview.general_flags)


def test_the_schedule_tells_which_days_the_class_met(tmp_path):
    assert schedule_meeting_days(_course(tmp_path).weeks) == (1, 3)  # Tue/Thu
    assert schedule_meeting_days(extract_course_data(build_minimal_syllabus(tmp_path / "w.docx")).weeks) == ()


def test_a_term_starting_on_tuesday_keeps_the_first_meeting_first(tmp_path):
    new_course, _ = roll_over_course(
        _course(tmp_path),
        target_term="Fall 2026",
        calendars=CALENDARS,
        manual_week1_date=dt.date(2026, 8, 25),  # a Tuesday
        meeting_days=(0, 2),
    )

    week1 = [w for w in _regular(new_course) if w.week_number == 1]
    assert [(w.topics, w.date) for w in week1] == [
        (["Topic 1a"], dt.date(2026, 8, 26)),  # Wed comes first in a week from Tuesday
        (["Topic 1b"], dt.date(2026, 8, 31)),
    ]
