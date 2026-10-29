"""Which weekdays a class meets, for rollover.

Classes can move days between terms (Tue/Thu one year, Mon/Wed the next),
so the instructor picks the target term's meeting days at rollover time.
A holiday or break is then flagged only when it lands on an actual class
day, instead of whenever it touches the week's start date. A schedule
with a row per class meeting has each meeting dated on those days
(chalk.rollover.preview). Days are `datetime.date.weekday()` numbers:
0 = Monday ... 6 = Sunday.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from collections.abc import Iterable

from chalk.models import Week

DAY_ABBREVIATIONS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

_DAY_NAMES = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tues": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thurs": 3, "thur": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}  # fmt: skip
# Registrar-style letter codes: "MWF", "TR", "TTh". "S" alone is ambiguous.
_CODE_LETTERS = {"M": 0, "T": 1, "Tu": 1, "W": 2, "R": 3, "Th": 3, "F": 4, "Sa": 5, "Su": 6}
_CODE_PART_RE = re.compile(r"Th|Tu|Sa|Su|[MTWRF]")


def parse_meeting_days(meeting_pattern: str) -> tuple[int, ...]:
    """Best-effort read of a syllabus's meeting pattern, e.g. "MW 10:45-12:05"
    or "Tuesdays and Thursdays" -> (0, 2) / (1, 3). Empty when it names no
    days ("Online async")."""
    days: set[int] = set()
    for token in re.findall(r"[A-Za-z]+", meeting_pattern):
        name = token.lower().removesuffix("s") if token.lower().endswith("days") else token.lower()
        if name in _DAY_NAMES:
            days.add(_DAY_NAMES[name])
            continue
        parts = _CODE_PART_RE.findall(token)
        if parts and "".join(parts) == token:
            days.update(_CODE_LETTERS[part] for part in parts)
    return tuple(sorted(days))


def schedule_meeting_days(weeks: Iterable[Week]) -> tuple[int, ...]:
    """The weekdays a class with a row per class meeting met on, read from
    its dated rows: the most common set of weekdays among the weeks with
    the most rows ("Week 2 (1/13)", "Week 2 (1/15)" -> Tue/Thu). Empty
    for a schedule with one row per week."""
    days_by_week: dict[int, set[int]] = {}
    for week in weeks:
        if week.meeting is not None and week.date is not None and not week.is_break:
            days_by_week.setdefault(week.week_number, set()).add(week.date.weekday())
    if not days_by_week:
        return ()
    most = max(len(days) for days in days_by_week.values())
    full_weeks = Counter(tuple(sorted(days)) for days in days_by_week.values() if len(days) == most)
    return full_weeks.most_common(1)[0][0]


def days_in_order_from(start: dt.date, days: Iterable[int]) -> list[int]:
    """`days` in the order they come in a week that begins on `start`'s
    weekday: from a Wednesday, Mon/Wed is (Wed, Mon)."""
    return sorted(days, key=lambda day: (day - start.weekday()) % 7)


def format_meeting_days(days: tuple[int, ...]) -> str:
    return "/".join(DAY_ABBREVIATIONS[day] for day in sorted(days))


def class_dates_in_week(week_date: dt.date, meeting_days: tuple[int, ...]) -> list[dt.date]:
    """The dates a class meets in the week containing `week_date`. With no
    meeting days known, the week's own date stands in for the whole week."""
    if not meeting_days:
        return [week_date]
    monday = week_date - dt.timedelta(days=week_date.weekday())
    return [monday + dt.timedelta(days=day) for day in sorted(meeting_days)]


def meeting_days_changed_flag(meeting_pattern: str, meeting_days: tuple[int, ...]) -> str | None:
    """Flag when the instructor picked different days than the syllabus lists,
    since the syllabus's meeting-pattern line is never rewritten."""
    listed = parse_meeting_days(meeting_pattern)
    if not listed or not meeting_days or set(listed) == set(meeting_days):
        return None
    return (
        f"The syllabus lists class meetings as \"{meeting_pattern}\", but this rollover checks "
        f"{format_meeting_days(meeting_days)} — update the meeting pattern in the syllabus by hand."
    )
