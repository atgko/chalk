"""Skipping a break the class takes off (Nov 9 UAT: the Fall → Spring
rollover warned that Week 9 fell in Spring Break, but the new syllabus
still had class that week and no Spring Break in its schedule).

Weeks are laid out one after another from the new term's first day.
When a break the class takes off covers every class day of a week, that
week and the ones after it move a week later, and the break gets a row
in the schedule, as the instructor would do by hand. A break that covers
only some class days (Thanksgiving on a Tue/Thu class) is still only
flagged: the class meets that week.

A syllabus that numbers its break weeks ("Week 10 — Spring Break") already
has a slot for its break, so moving weeks too would add a second one; its
weeks are left in place and flagged as before.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from chalk.models import Week
from chalk.rollover.season_change import format_break_label

_BREAK_MENTION_RE = re.compile(
    r"\b(?:spring|fall|summer|winter|thanksgiving|holiday)\s+break\b|\bno class(?:es)?\b", re.IGNORECASE
)
_WEEKDAYS = (0, 1, 2, 3, 4)
_DAYS_IN_A_WEEK = 7


@dataclass(frozen=True)
class SkippedBreak:
    """A break the schedule steps over: `entry` is its calendar entry, and
    `week_number` the first week that moved past it."""

    entry: dict
    week_number: int

    @property
    def start(self) -> dt.date:
        return dt.date.fromisoformat(self.entry["date_start"])

    @property
    def end(self) -> dt.date:
        return dt.date.fromisoformat(self.entry["date_end"])


def has_numbered_break_weeks(weeks: list[Week]) -> bool:
    """Whether a numbered week is a break ("Week 10 — Spring Break")."""
    return any(
        not week.is_break and _BREAK_MENTION_RE.search(" ".join([*week.topics, *week.assignments, week.notes or ""]))
        for week in weeks
    )


def plan_week_starts(
    week_numbers: list[int],
    term_start: dt.date,
    breaks_taken: list[dict],
    meeting_days: tuple[int, ...],
) -> tuple[dict[int, dt.date], list[SkippedBreak]]:
    """Each week number's first day in the new term, one week apart from
    `term_start`, stepping over any break in `breaks_taken` (multi-day
    calendar entries) that covers all of that week's class days. Returns
    the start dates and the breaks stepped over."""
    starts: dict[int, dt.date] = {}
    skipped: list[SkippedBreak] = []
    shift = 0
    for number in sorted(set(week_numbers)):
        start = term_start + dt.timedelta(days=_DAYS_IN_A_WEEK * (number - 1 + shift))
        covering = _break_covering(start, breaks_taken, meeting_days)
        while covering is not None:
            skipped.append(SkippedBreak(covering, number))
            shift += 1
            start += dt.timedelta(days=_DAYS_IN_A_WEEK)
            covering = _break_covering(start, breaks_taken, meeting_days)
        starts[number] = start
    return starts, skipped


def break_rows_for(skipped: list[SkippedBreak], existing: list[Week]) -> list[Week]:
    """A schedule row for each break stepped over that the schedule
    doesn't already show."""
    shown = {(week.date_start, week.date_end) for week in existing if week.is_break}
    rows = []
    for item in skipped:
        if (item.start, item.end) in shown:
            continue
        shown.add((item.start, item.end))
        rows.append(
            Week(
                label=format_break_label(item.entry["label"], item.start, item.end),
                is_break=True,
                date_start=item.start,
                date_end=item.end,
            )
        )
    return rows


def skipped_break_flags(skipped: list[SkippedBreak], added: list[Week]) -> list[str]:
    """Say which weeks moved for which break, and how to undo it."""
    added_spans = {(week.date_start, week.date_end) for week in added}
    flags = []
    for item in skipped:
        label = item.entry["label"]
        row_note = f" and a {label} row is added to the schedule" if (item.start, item.end) in added_spans else ""
        flags.append(
            f"{label} ({_short(item.start)} – {_short(item.end)}) covers Week {item.week_number}'s class days, "
            f"so Week {item.week_number} and the weeks after it move a week later{row_note}. If the class meets "
            f'through {label}, turn off "Class takes {label} off".'
        )
    return flags


MOVE_PAST_BREAKS_LABEL = "Move weeks past a break that covers a whole week of class"


def move_past_breaks_hints(would_skip: list[SkippedBreak]) -> list[str]:
    """When moving weeks past breaks is off: which breaks cover a whole
    week of class, and how to have Chalk move the weeks instead."""
    return [
        f"{item.entry['label']} ({_short(item.start)} – {_short(item.end)}) covers all of Week "
        f"{item.week_number}'s class days. To move Week {item.week_number} and the weeks after it a week "
        f'later and add a {item.entry["label"]} row, tick "{MOVE_PAST_BREAKS_LABEL}" and preview again.'
        for item in _first_per_break(would_skip)
    ]


def _first_per_break(skipped: list[SkippedBreak]) -> list[SkippedBreak]:
    seen, first = set(), []
    for item in skipped:
        key = (item.start, item.end)
        if key not in seen:
            seen.add(key)
            first.append(item)
    return first


def past_term_end_flag(weeks: list[Week], term_end: dt.date | None, target_term: str) -> str | None:
    """A flag when the last class now falls after the term ends."""
    dated = [week for week in weeks if not week.is_break and week.date is not None]
    if term_end is None or not dated:
        return None
    last = max(dated, key=lambda week: week.date)
    if last.date <= term_end:
        return None
    return (
        f"Week {last.week_number} ({_short(last.date)}) is after {target_term} ends ({_short(term_end)}). "
        "Shorten the course, let the class meet through a break, or change the dates in the table."
    )


def _break_covering(week_start: dt.date, breaks: list[dict], meeting_days: tuple[int, ...]) -> dict | None:
    days = _class_days(week_start, meeting_days)
    for entry in breaks:
        start = dt.date.fromisoformat(entry["date_start"])
        end = dt.date.fromisoformat(entry["date_end"])
        if days and all(start <= day <= end for day in days):
            return entry
    return None


def _class_days(week_start: dt.date, meeting_days: tuple[int, ...]) -> list[dt.date]:
    """The days the class could meet in the 7 days from `week_start`: the
    picked meeting days, or every weekday when none were picked."""
    wanted = meeting_days or _WEEKDAYS
    window = (week_start + dt.timedelta(days=offset) for offset in range(_DAYS_IN_A_WEEK))
    return [day for day in window if day.weekday() in wanted]


def _short(day: dt.date) -> str:
    return f"{day.strftime('%b')} {day.day}"
