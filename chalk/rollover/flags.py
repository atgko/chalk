"""Flags a rollover raises for human confirmation (F-02).

Each helper either returns flag sentences or appends them to the matching
WeekChange in a RolloverPreview (chalk.rollover.preview). None of them
changes a date — they only point at things the instructor should check.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING

from chalk.models import CourseData, Week
from chalk.rollover.meeting_days import class_dates_in_week, meeting_days_changed_flag

if TYPE_CHECKING:
    from chalk.rollover.preview import WeekChange

_DST_BOUNDARY_WINDOW_DAYS = 14
_BREAK_MENTION_RE = re.compile(
    r"\b(?:spring|fall|summer|winter|thanksgiving|holiday)\s+break\b|\bno class(?:es)?\b", re.IGNORECASE
)


def flag_weeks_colliding_with_target_breaks(
    weeks: list[Week],
    changes: list[WeekChange],
    target_breaks: list[dict],
    year: int,
    meeting_days: tuple[int, ...],
) -> None:
    changes_by_week_number = {c.week_number: c for c in changes if c.week_number is not None}
    for week in weeks:
        if week.is_break or week.date is None:
            continue
        class_dates = class_dates_in_week(week.date, meeting_days)
        for entry in target_breaks:
            if any(_date_in_break(class_date, entry) for class_date in class_dates):
                changes_by_week_number[week.week_number].flags.append(
                    f"{entry['label']} {year} is {_format_break_range(entry)} — "
                    f"confirm Week {week.week_number} timing"
                )


def flag_numbered_weeks_marked_as_breaks(
    weeks: list[Week], changes: list[WeekChange], source_term: str, target_term: str
) -> None:
    """Some syllabi number their break week ("Week 10 (Mar. 10) — Spring
    Break"), so it rolls over as an ordinary week whose content is a break
    that's probably no longer in that week. Flag it rather than guess."""
    changes_by_week_number = {c.week_number: c for c in changes if c.week_number is not None}
    for week in weeks:
        if week.is_break or week.week_number not in changes_by_week_number:
            continue
        match = _BREAK_MENTION_RE.search(" ".join([*week.topics, *week.assignments, week.notes or ""]))
        if match:
            changes_by_week_number[week.week_number].flags.append(
                f"Week {week.week_number} was marked '{match.group(0)}' in {source_term} — check "
                f"this week against the {target_term} calendar."
            )


def _date_in_break(date: dt.date, entry: dict) -> bool:
    if "date" in entry:
        return date == dt.date.fromisoformat(entry["date"])
    if "date_start" in entry and "date_end" in entry:
        return dt.date.fromisoformat(entry["date_start"]) <= date <= dt.date.fromisoformat(
            entry["date_end"]
        )
    return False  # pragma: no cover - calendars.json entries always have one or the other


def _format_break_range(entry: dict) -> str:
    if "date" in entry:
        d = dt.date.fromisoformat(entry["date"])
        return f"{d.strftime('%b')} {d.day}"
    start = dt.date.fromisoformat(entry["date_start"])
    end = dt.date.fromisoformat(entry["date_end"])
    return f"{start.strftime('%b')} {start.day}–{end.day}"


def duration_change_flags(old_duration: int, new_duration: int) -> list[str]:
    if old_duration == new_duration:
        return []
    return [
        f"Course length changed from {old_duration} to {new_duration} weeks. "
        "Review quiz, exam, and lab numbering in the assignments below — "
        "the tool never renumbers them automatically."
    ]


def schedule_choice_flags(
    course_data: CourseData,
    meeting_days: tuple[int, ...],
    breaks_not_observed: frozenset[str],
    dropped_breaks: list[str],
) -> list[str]:
    flags = []
    if breaks_not_observed:
        removed = f" Removed from the schedule: {', '.join(dropped_breaks)}." if dropped_breaks else ""
        flags.append(
            f"This class meets through {', '.join(sorted(breaks_not_observed))}, so "
            f"{'it is' if len(breaks_not_observed) == 1 else 'they are'} not treated as a break.{removed}"
        )
    meeting_flag = meeting_days_changed_flag(course_data.course.meeting_pattern, meeting_days)
    if meeting_flag:
        flags.append(meeting_flag)
    return flags


def _first_sunday_of_november(year: int) -> dt.date:
    november_first = dt.date(year, 11, 1)
    days_until_sunday = (6 - november_first.weekday()) % 7
    return november_first + dt.timedelta(days=days_until_sunday)


def flag_dst_boundary_weeks(weeks: list[Week], changes: list[WeekChange]) -> None:
    """Markdown-only (PRD section 6.2): flag any week with assignments
    that falls within two weeks of the DST boundary, for human review.
    Never automates a timezone suffix."""
    changes_by_week_number = {c.week_number: c for c in changes if c.week_number is not None}
    for week in weeks:
        if week.is_break or week.date is None or not week.assignments:
            continue
        boundary = _first_sunday_of_november(week.date.year)
        if abs((week.date - boundary).days) <= _DST_BOUNDARY_WINDOW_DAYS:
            changes_by_week_number[week.week_number].flags.append(
                "This week's assignments fall within two weeks of the DST "
                "boundary (first Sunday of November). Double-check due "
                "times/timezones by hand — this is never automated."
            )
