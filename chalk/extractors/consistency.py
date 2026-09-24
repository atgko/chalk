"""Term-label vs Week-1-date consistency check (F-01, PRD section 6.1).

Named test case: the sponsor's own Spring 2026 syllabus carried Fall 2025
schedule dates — the term label had been updated for the new semester but
the schedule table had not. This check exists specifically to catch that
class of mistake before it reaches Canvas.

It never raises. A mismatch is a warning the instructor confirms or
corrects (PRD's "[Continue anyway] [Cancel]" prompt), not a hard failure —
callers decide what to do with a failed ConsistencyResult.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from chalk.models import CourseData, Week

_SEASON_START_MONTHS = {
    "fall": {8, 9},
    "spring": {1, 2},
    "summer": {5, 6},
}

_SEASON_RE = re.compile(r"\b(fall|spring|summer)\b", re.IGNORECASE)

_MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


@dataclass(frozen=True)
class ConsistencyResult:
    passed: bool
    term: str
    week1_date: dt.date | None
    detail: str | None = None


def check_term_consistency(course_data: CourseData) -> ConsistencyResult:
    """Compare the term label's season (Fall/Spring/Summer) against Week
    1's month. Returns a ConsistencyResult; a mismatch sets passed=False
    with a human-readable `detail` explaining the conflict.

    If the term label has no recognizable season word, or there's no
    regular Week 1 row to compare against, the check can't meaningfully
    evaluate anything — that's treated as passing rather than raising a
    spurious warning about something genuinely unknowable.
    """
    term = course_data.course.term
    week1 = _find_week_one(course_data)

    season_match = _SEASON_RE.search(term)
    if not season_match or week1 is None:
        return ConsistencyResult(
            passed=True, term=term, week1_date=week1.date if week1 else None
        )

    season = season_match.group(1).lower()
    if week1.date.month in _SEASON_START_MONTHS[season]:
        return ConsistencyResult(passed=True, term=term, week1_date=week1.date)

    likely_season = _likely_season_for_month(week1.date.month)
    detail = (
        f'Term label says: "{term}"\n'
        f"Week 1 date is:  {_MONTH_NAMES[week1.date.month]} {week1.date.day} "
        f"— this is a {likely_season} semester start.\n\n"
        "This usually means the term label was updated but the schedule "
        "table was not. Check which is correct before continuing."
    )
    return ConsistencyResult(passed=False, term=term, week1_date=week1.date, detail=detail)


def _find_week_one(course_data: CourseData) -> Week | None:
    for week in course_data.weeks:
        if not week.is_break and week.week_number == 1:
            return week
    return None


def _likely_season_for_month(month: int) -> str:
    for season, months in _SEASON_START_MONTHS.items():
        if month in months:
            return season
    # Outside any season's typical *start* window — best-effort guess for
    # the message text only; the pass/fail verdict above never reaches
    # this branch with an already-plausible month.
    if month in (10, 11, 12):
        return "fall"
    if month in (3, 4):
        return "spring"
    return "summer"
