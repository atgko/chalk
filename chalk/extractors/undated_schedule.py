"""Dating a schedule that has no dates of its own.

Some syllabi number their class meetings ("Meeting 1" to "Meeting 10")
without saying when they fall (UAT of PR #18, IS 6490). Every Chalk
feature works from dated weeks, so the weeks get dates: one week apart
from a Week 1 date, moving past any multi-day break in the term's
calendar (Fall Break, Spring Break), each of which becomes a break row.
Single-day holidays don't move a week; rollover flags those as usual.

The extractor gives the weeks provisional dates from the season
(`provisional_week1`), since it has no calendar. The pipeline then dates
them from the term's first day of classes (`default_week1`), and the
Review tab lets the instructor change Week 1, which re-dates the rest.
The course is marked `undated_schedule`, so Review keeps asking.
"""

from __future__ import annotations

import datetime as dt
import re

from chalk.calendar_data import find_term
from chalk.models import CourseData, CourseInfo, Week
from chalk.rollover.meeting_days import parse_meeting_days
from chalk.rollover.season_change import format_break_label, multi_day_breaks, season_of

_ONE_WEEK = dt.timedelta(weeks=1)
_YEAR_RE = re.compile(r"\b(\d{4})\b")
# The earliest a season's classes start, for a term not in the calendar:
# Week 1 is the first Monday on or after it.
_SEASON_EARLIEST_START = {"spring": (1, 7), "summer": (5, 13), "fall": (8, 20)}


def provisional_week1(term: str, year: int) -> dt.date:
    """A plausible Week 1 for `term` without a calendar: the first Monday
    on or after the season's earliest start (January 7 if no season)."""
    month, day = _SEASON_EARLIEST_START.get((season_of(term) or "").lower(), (1, 7))
    return _next_weekday(dt.date(year, month, day), (0,))


def default_week1(course: CourseInfo, calendars: dict) -> dt.date:
    """Week 1 for an undated schedule: the term's first day of classes
    from the calendar (else the season guess), moved to the first day the
    class meets, if the syllabus says."""
    entry = find_term(calendars, course.term)
    if entry:
        start = dt.date.fromisoformat(entry["start"])
    else:
        year = _YEAR_RE.search(course.term)
        start = provisional_week1(course.term, int(year.group(1)) if year else course.term_start.year)
    return _next_weekday(start, parse_meeting_days(course.meeting_pattern))


def date_undated_schedule(course_data: CourseData, week1: dt.date, calendars: dict) -> CourseData:
    """The course with its weeks dated a week apart from `week1`, skipping
    the weeks of the term's multi-day breaks, which become break rows."""
    entry = find_term(calendars, course_data.course.term)
    breaks = [
        (dt.date.fromisoformat(b["date_start"]), dt.date.fromisoformat(b["date_end"]), b["label"])
        for b in multi_day_breaks(entry.get("no_class_dates", []) if entry else [])
    ]
    weeks: list[Week] = []
    added: set[tuple] = set()
    when = week1
    for week in (w for w in course_data.weeks if not w.is_break):
        while (hit := next((b for b in breaks if b[0] <= when <= b[1]), None)) is not None:
            if hit not in added:  # a break longer than a week is one row
                start, end, label = hit
                weeks.append(
                    Week(label=format_break_label(label, start, end), is_break=True, date_start=start, date_end=end)
                )
                added.add(hit)
            when += _ONE_WEEK
        weeks.append(week.model_copy(update={"date": when}))
        when += _ONE_WEEK
    dated = [w.date for w in weeks if not w.is_break]
    course = course_data.course.model_copy(update={"term_start": dated[0], "term_end": dated[-1]})
    return course_data.model_copy(update={"course": course, "weeks": weeks})


def _next_weekday(start: dt.date, weekdays: tuple[int, ...]) -> dt.date:
    """The first date on or after `start` that falls on one of `weekdays`
    (0 = Monday); `start` itself when none are given."""
    if not weekdays:
        return start
    return next(day for offset in range(7) if (day := start + dt.timedelta(days=offset)).weekday() in weekdays)
