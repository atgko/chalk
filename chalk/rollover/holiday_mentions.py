"""Holidays the old term had that the syllabus still mentions (Nov 9 UAT:
a Fall → Spring syllabus "still called out a Labor Day … and Fall Break
still shows up", while MLK Day and Presidents' Day didn't).

The schedule's break rows and a University Dates table are rewritten from
the new term's calendar. Anywhere else, a sentence like "No class on Labor
Day" can't be rewritten safely, so the preview lists those lines and the
new term's holidays and breaks, for the instructor to update by hand.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable

from chalk.calendar_data import find_term
from chalk.models import CourseData
from chalk.rollover.season_change import is_season_change

_MAX_LINES = 5
_LINE_LENGTH = 120
# A bare "Thanksgiving" counts as Thanksgiving Break.
_SHORT_NAMES = {"Thanksgiving Break": "Thanksgiving"}


def stale_holiday_flag(lines: Iterable[str], course_data: CourseData, target_term: str, calendars: dict) -> str | None:
    """A note listing lines that name a holiday or break of the old term
    that the new term doesn't have, or None (same season, a term missing
    from the calendar, or no such lines)."""
    source = find_term(calendars, course_data.course.term)
    target = find_term(calendars, target_term)
    if source is None or target is None or not is_season_change(course_data.course.term, target_term):
        return None
    new_names = {_core(entry["label"]) for entry in target["no_class_dates"]}
    old_names = [
        name
        for entry in source["no_class_dates"]
        if _core(entry["label"]) not in new_names
        for name in (entry["label"], _SHORT_NAMES.get(entry["label"]))
        if name
    ]
    if not old_names:
        return None
    pattern = re.compile(r"\b(" + "|".join(re.escape(name) for name in old_names) + r")\b", re.IGNORECASE)
    rewritten = _rewritten_lines(course_data)
    found: list[str] = []
    named: list[str] = []
    for line in lines:
        text = " ".join(line.split())
        match = pattern.search(text)
        if not match or text in rewritten or text in found:
            continue
        found.append(text if len(text) <= _LINE_LENGTH else text[: _LINE_LENGTH - 1] + "…")
        name = _canonical(match.group(1), old_names)
        if name not in named:
            named.append(name)
        if len(found) == _MAX_LINES:
            break
    if not found:
        return None
    quoted = "; ".join(f'"{text}"' for text in found)
    holidays = ", ".join(_describe(entry) for entry in target["no_class_dates"])
    return (
        f"These lines still mention {' or '.join(named)}, which {target_term} doesn't have: {quoted}. "
        f"{target_term}'s holidays and breaks are {holidays}. Update these lines by hand."
    )


def _rewritten_lines(course_data: CourseData) -> set[str]:
    """Text the rollover rewrites itself: University Dates events and the
    schedule's break rows."""
    events = {entry.event for entry in course_data.university_dates}
    break_labels = {week.label for week in course_data.weeks if week.is_break}
    return {" ".join(text.split()) for text in events | break_labels}


def _core(label: str) -> str:
    return re.sub(r"\s*\(.*?\)\s*", " ", label).strip().lower()


def _canonical(found: str, names: list[str]) -> str:
    for name in names:
        if name.lower() == found.lower():
            return next((full for full, short in _SHORT_NAMES.items() if short == name), name)
    return found  # pragma: no cover - the pattern only matches these names


def _describe(entry: dict) -> str:
    if "date" in entry:
        return f"{entry['label']} ({_short(dt.date.fromisoformat(entry['date']))})"
    start, end = dt.date.fromisoformat(entry["date_start"]), dt.date.fromisoformat(entry["date_end"])
    return f"{entry['label']} ({_short(start)} – {_short(end)})"


def _short(day: dt.date) -> str:
    return f"{day.strftime('%b')} {day.day}"
