"""Break handling for rollovers into a different season (e.g. Fall 2026 ->
Spring 2027).

A same-season rollover keeps the syllabus's own break rows and just moves
their dates (chalk.rollover.preview). Across seasons that would carry
"Fall Break" into a Spring syllabus, so instead the break rows are rebuilt
from the target term's calendar: every multi-day break that overlaps the
course's new dates becomes a break row, and the old ones are dropped. A
syllabus that listed no breaks at all is left without them — the
instructor evidently doesn't track breaks in the schedule.

Single-day holidays in the University Dates table (e.g. Labor Day) work
the same way: each one takes over the next target-term holiday, and any
target-term holiday left over is flagged so the instructor can add a row.
"""

from __future__ import annotations

import datetime as dt
import re

from chalk.models import Week

_SEASON_RE = re.compile(r"\b(fall|spring|summer)\b", re.IGNORECASE)
_DAYS_IN_WEEK_AFTER_START = 6


def season_of(term: str) -> str | None:
    """The term's season, e.g. "Fall 2026" -> "Fall"; None if it names none."""
    match = _SEASON_RE.search(term)
    return match.group(1).capitalize() if match else None


def is_season_change(source_term: str, target_term: str) -> bool:
    source, target = season_of(source_term), season_of(target_term)
    return source is not None and target is not None and source != target


def multi_day_breaks(target_breaks: list[dict]) -> list[dict]:
    """The target term's break spans (not single-day holidays), in date order."""
    spans = [entry for entry in target_breaks if "date_start" in entry and "date_end" in entry]
    return sorted(spans, key=lambda entry: entry["date_start"])


def single_day_holidays(target_breaks: list[dict]) -> list[dict]:
    """The target term's single-day holidays (e.g. Labor Day), in date order."""
    holidays = [entry for entry in target_breaks if "date" in entry]
    return sorted(holidays, key=lambda entry: entry["date"])


def holiday_names(calendars: dict) -> frozenset[str]:
    """Every single-day holiday named in any term of the calendar data,
    normalized — what tells a holiday row ("Labor Day") apart from a
    deadline ("Last day to drop") in the University Dates table."""
    return frozenset(
        normalize_label(entry["label"])
        for term in calendars.get("terms", [])
        for entry in term.get("no_class_dates", [])
        if "date" in entry
    )


def is_holiday_name(label: str, known_holidays: frozenset[str]) -> bool:
    return any(_labels_match(label, name) for name in known_holidays)


def match_calendar_entry(label: str, entries: list[dict]) -> dict | None:
    """The first entry whose label matches `label` (see `_labels_match`)."""
    return next((entry for entry in entries if _labels_match(label, entry["label"])), None)


def _labels_match(first: str, second: str) -> bool:
    """True when either label contains the other once normalized, e.g.
    "Labor Day (no class)" and "Labor Day". A label with no letters
    matches nothing."""
    first, second = normalize_label(first), normalize_label(second)
    return bool(first and second) and (first in second or second in first)


def normalize_label(label: str) -> str:
    return re.sub(r"[^a-z ]", "", label.lower()).strip()


def format_break_label(name: str, start: dt.date, end: dt.date) -> str:
    return f"{name} ({start.month}/{start.day} - {end.month}/{end.day})"


def rebuild_break_weeks(target_breaks: list[dict], regular_weeks: list[Week]) -> list[Week]:
    """One break Week per target-term break overlapping the span from the
    first regular week's start to the last regular week's end."""
    dated = [week.date for week in regular_weeks if week.date is not None]
    if not dated:
        return []
    first_day = min(dated)
    last_day = max(dated) + dt.timedelta(days=_DAYS_IN_WEEK_AFTER_START)

    new_breaks = []
    for entry in multi_day_breaks(target_breaks):
        start = dt.date.fromisoformat(entry["date_start"])
        end = dt.date.fromisoformat(entry["date_end"])
        if start <= last_day and end >= first_day:
            new_breaks.append(
                Week(
                    label=format_break_label(entry["label"], start, end),
                    is_break=True,
                    date_start=start,
                    date_end=end,
                )
            )
    return new_breaks


def replacement_flag(
    source_term: str, target_term: str, removed: list[str], added: list[str]
) -> str:
    added_text = ", ".join(added) if added else "none (no breaks fall within the course dates)"
    return (
        f"This is a {season_of(source_term)} → {season_of(target_term)} rollover, so breaks come "
        f"from the {target_term} calendar. Removed: {', '.join(removed)}. Added: {added_text}."
    )


def stale_break_flag(source_term: str, target_term: str, break_names: list[str]) -> str:
    return (
        f"{', '.join(break_names)} came from a {season_of(source_term)} syllabus, and {target_term} "
        "isn't in the calendar data — rename or remove the break rows by hand."
    )


def unmatched_university_date_flag(event: str, target_term: str) -> str:
    return (
        f"'{event}' isn't on the {target_term} calendar — check or remove it in the "
        "University Dates table."
    )


def missing_holiday_flag(holidays: list[dict], target_term: str) -> str:
    names = ", ".join(f"{entry['label']} ({_month_day(entry['date'])})" for entry in holidays)
    return f"{target_term} also has {names} — add a row to the University Dates table if you list holidays."


def _month_day(iso_date: str) -> str:
    date = dt.date.fromisoformat(iso_date)
    return f"{date.month}/{date.day}"
