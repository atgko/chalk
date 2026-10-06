"""Tests for the instructor's rollover schedule choices (sponsor feedback):
which days the class meets, so holiday warnings only fire on real class
days, and which breaks the class meets through (some graduate programs
don't take Fall/Spring Break)."""

import datetime as dt

import pytest

from chalk.rollover.meeting_days import (
    class_dates_in_week,
    format_meeting_days,
    meeting_days_changed_flag,
    parse_meeting_days,
)
from chalk.rollover.preview import roll_over_course
from tests.test_rollover_preview import CALENDARS, _is6640_ten_week_course, _with_university_dates
from tests.test_rollover_season_change import CALENDARS as SEASON_CALENDARS
from tests.test_rollover_season_change import _course

MON, TUE, WED, THU, FRI = range(5)


# ---- parsing meeting patterns ----------------------------------------------------


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("MW 10:45-12:05", (MON, WED)),
        ("TR 2:00 PM", (TUE, THU)),
        ("TTh 9:10-10:30", (TUE, THU)),
        ("MWF", (MON, WED, FRI)),
        ("Tuesdays and Thursdays, 6-9pm", (TUE, THU)),
        ("Mon/Wed", (MON, WED)),
        ("Wednesday evenings", (WED,)),
        ("Online async", ()),
        ("", ()),
        ("TBA, Room WEB 1230", ()),
    ],
)
def test_parse_meeting_days(pattern, expected):
    assert parse_meeting_days(pattern) == expected


def test_format_meeting_days():
    assert format_meeting_days((THU, TUE)) == "Tue/Thu"


def test_class_dates_in_week_use_the_meeting_days_of_that_week():
    week_start = dt.date(2027, 8, 30)  # a Monday

    assert class_dates_in_week(week_start, (TUE, THU)) == [dt.date(2027, 8, 31), dt.date(2027, 9, 2)]
    assert class_dates_in_week(week_start, ()) == [week_start]


def test_meeting_days_changed_flag_only_when_the_syllabus_named_other_days():
    assert meeting_days_changed_flag("MW 10:45", (TUE, THU)) is not None
    assert meeting_days_changed_flag("MW 10:45", (MON, WED)) is None
    assert meeting_days_changed_flag("Online async", (TUE, THU)) is None
    assert meeting_days_changed_flag("MW 10:45", ()) is None


# ---- meeting days narrow the holiday warnings -----------------------------------


def _flags_by_week(preview) -> dict[int, list[str]]:
    return {c.week_number: c.flags for c in preview.week_changes if c.week_number is not None}


def test_without_meeting_days_a_monday_holiday_is_flagged_from_the_week_start():
    # Week 3 of Fall 2027 starts Mon Sep 6 — Labor Day.
    _, preview = roll_over_course(_is6640_ten_week_course(), target_term="Fall 2027", calendars=CALENDARS)

    assert any("Labor Day" in flag for flag in _flags_by_week(preview)[3])


def test_a_tue_thu_class_is_not_warned_about_a_monday_holiday():
    _, preview = roll_over_course(
        _is6640_ten_week_course(), target_term="Fall 2027", calendars=CALENDARS, meeting_days=(TUE, THU)
    )

    assert _flags_by_week(preview)[3] == []


def test_a_mon_wed_class_is_warned_about_a_monday_holiday():
    _, preview = roll_over_course(
        _is6640_ten_week_course(), target_term="Fall 2027", calendars=CALENDARS, meeting_days=(MON, WED)
    )

    assert any("Labor Day 2027 is Sep 6" in flag for flag in _flags_by_week(preview)[3])


def test_a_break_covering_a_class_day_mid_week_is_flagged():
    # Week 8 starts Mon Oct 11; Fall Break 2027 runs Sat Oct 9 – Sun Oct 17.
    _, preview = roll_over_course(
        _is6640_ten_week_course(), target_term="Fall 2027", calendars=CALENDARS, meeting_days=(THU,)
    )

    flags = _flags_by_week(preview)
    assert any("Fall Break" in flag and "Week 8" in flag for flag in flags[8])
    assert flags[7] == [] and flags[9] == []


def test_thanksgiving_is_caught_for_a_thursday_class_even_though_the_week_starts_monday():
    fall_course = _course(term="Fall 2026", term_start=dt.date(2026, 8, 24), weeks_count=16, breaks=[])

    _, without_days = roll_over_course(fall_course, target_term="Fall 2027", calendars=SEASON_CALENDARS)
    _, thursdays = roll_over_course(
        fall_course, target_term="Fall 2027", calendars=SEASON_CALENDARS, meeting_days=(THU,)
    )

    # Week 14 starts Mon Nov 22, 2027; Thanksgiving Break is Thu Nov 25 – Sun Nov 28.
    assert not any("Thanksgiving" in flag for flag in _flags_by_week(without_days)[14])
    assert any("Thanksgiving" in flag for flag in _flags_by_week(thursdays)[14])


def test_picking_days_that_differ_from_the_syllabus_adds_a_reminder():
    course = _is6640_ten_week_course()
    course = course.model_copy(
        update={"course": course.course.model_copy(update={"meeting_pattern": "MW 9:00"})}
    )

    _, preview = roll_over_course(
        course, target_term="Fall 2027", calendars=CALENDARS, meeting_days=(TUE, THU)
    )

    assert any("Tue/Thu" in flag and "MW 9:00" in flag for flag in preview.general_flags)


# ---- breaks the class meets through ---------------------------------------------


def test_a_break_not_observed_is_dropped_from_the_schedule_and_not_flagged():
    new_course_data, preview = roll_over_course(
        _is6640_ten_week_course(),
        target_term="Fall 2027",
        calendars=CALENDARS,
        breaks_not_observed=frozenset({"Fall Break"}),
    )

    assert [week for week in new_course_data.weeks if week.is_break] == []
    assert all("Fall Break" not in flag for flag in _flags_by_week(preview)[8])
    assert any(
        "meets through Fall Break" in flag and "Removed from the schedule: Fall Break" in flag
        for flag in preview.general_flags
    )


def test_single_day_holidays_are_still_flagged_when_a_break_is_not_observed():
    _, preview = roll_over_course(
        _is6640_ten_week_course(),
        target_term="Fall 2027",
        calendars=CALENDARS,
        breaks_not_observed=frozenset({"Fall Break"}),
    )

    assert any("Labor Day" in flag for flag in _flags_by_week(preview)[3])


def test_university_dates_still_list_a_break_the_class_meets_through():
    new_course_data, _ = roll_over_course(
        _with_university_dates(_is6640_ten_week_course()),
        target_term="Fall 2027",
        calendars=CALENDARS,
        breaks_not_observed=frozenset({"Fall Break"}),
    )

    fall_break = next(d for d in new_course_data.university_dates if d.event == "Fall Break")
    assert (fall_break.date_start, fall_break.date_end) == (dt.date(2027, 10, 9), dt.date(2027, 10, 17))


def test_season_change_only_adds_the_breaks_the_class_observes():
    spring_course = _course(
        term="Spring 2027",
        term_start=dt.date(2027, 1, 11),
        weeks_count=16,
        breaks=[("Spring Break", dt.date(2027, 3, 6), dt.date(2027, 3, 14))],
    )

    new_course_data, _ = roll_over_course(
        spring_course,
        target_term="Fall 2027",
        calendars=SEASON_CALENDARS,
        breaks_not_observed=frozenset({"Fall Break"}),
    )

    assert [week.label for week in new_course_data.weeks if week.is_break] == [
        "Thanksgiving Break (11/25 - 11/28)"
    ]
