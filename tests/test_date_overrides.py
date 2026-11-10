"""The instructor's own dates at rollover (Nov 9 UAT)."""

import datetime as dt

import pytest

from chalk.rollover.date_overrides import override_week_dates
from chalk.rollover.preview import roll_over_course
from tests.test_rollover_preview import CALENDARS, _is6640_ten_week_course


def _rollover():
    return roll_over_course(_is6640_ten_week_course(), target_term="Fall 2027", calendars=CALENDARS)


def _dates(preview):
    return [change.new_date for change in preview.week_changes]


def test_a_changed_date_moves_that_week_and_relabels_it():
    course, preview = _rollover()
    dates = _dates(preview)
    week3 = next(i for i, change in enumerate(preview.week_changes) if change.week_number == 3)
    dates[week3] = dt.date(2027, 9, 8)

    new_course, new_preview = override_week_dates(course, preview, dates)

    week = next(w for w in new_course.weeks if w.week_number == 3)
    assert (week.date, week.label) == (dt.date(2027, 9, 8), "Week 3 (9/8)")
    assert new_preview.week_changes[week3].new_date == dt.date(2027, 9, 8)
    assert new_preview.week_changes[week3].label == "Week 3 (9/8)"
    assert any(flag.startswith("You changed the date of Week 3.") for flag in new_preview.general_flags)


def test_the_last_weeks_new_date_sets_the_terms_end():
    course, preview = _rollover()
    dates = _dates(preview)
    last = max(range(len(dates)), key=lambda i: preview.week_changes[i].week_number or 0)
    dates[last] = dt.date(2027, 11, 3)

    new_course, _ = override_week_dates(course, preview, dates)

    assert new_course.course.term_end == dt.date(2027, 11, 3)


def test_unchanged_dates_return_the_same_plan():
    course, preview = _rollover()

    assert override_week_dates(course, preview, _dates(preview)) == (course, preview)
    assert override_week_dates(course, preview, [None] * len(preview.week_changes)) == (course, preview)


def test_break_rows_keep_the_calendars_dates():
    course, preview = _rollover()
    dates = _dates(preview)
    breaks = [i for i, change in enumerate(preview.week_changes) if change.week_number is None]
    assert breaks
    for i in breaks:
        dates[i] = dt.date(2027, 1, 1)

    assert override_week_dates(course, preview, dates) == (course, preview)


def test_the_dates_must_match_the_rows():
    course, preview = _rollover()

    with pytest.raises(ValueError, match="One date is needed per row"):
        override_week_dates(course, preview, [])
