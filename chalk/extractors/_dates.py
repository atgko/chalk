"""Small date-parsing primitives shared by the Word and markdown
extractors. Each extractor wraps these with its own error messages —
what's shared here is just the regex/parsing logic, not the fail-loud
behavior, since the two formats surface errors in slightly different
contexts.
"""

from __future__ import annotations

import datetime as dt
import re

from chalk.models import Week

# A loose M/D - M/D range (hyphen, en dash, or em dash), e.g.
# "10/10 - 10/18" or "10/10-10/18".
DATE_RANGE_RE = re.compile(r"(\d{1,2})/(\d{1,2})\s*[-–—]\s*(\d{1,2})/(\d{1,2})")

# A full M/D/YYYY date, e.g. "8/24/2026".
FULL_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

# Any 4-digit year, used to recover a calendar year from a term label like
# "Fall 2026" (the label carries the year explicitly so the term/Week-1
# consistency check has two independent sources to compare).
_YEAR_RE = re.compile(r"(\d{4})")


def year_from_term(term: str) -> int | None:
    """Extract the 4-digit year from a term label, or None if it has none."""
    match = _YEAR_RE.search(term)
    return int(match.group(1)) if match else None


# A row dated this far before the row above it means the schedule crossed
# New Year, not that the rows are out of order.
_NEW_YEAR_GAP = dt.timedelta(days=180)
_DATE_FIELDS = ("date", "date_start", "date_end")


def roll_dates_past_new_year(weeks: list[Week]) -> list[Week]:
    """Schedule rows are read with the term's year, but a schedule that runs
    past December (a Fall course whose finals week is in January, or a
    break from Dec 20 to Jan 3) needs the next year for the later dates.
    Walk the rows in order and add a year from the first date that falls
    far before the previous one."""
    result: list[Week] = []
    previous: dt.date | None = None
    extra_years = 0
    for week in weeks:
        updates = {}
        for field in _DATE_FIELDS:
            value = getattr(week, field)
            if value is None:
                continue
            value = value.replace(year=value.year + extra_years)
            if previous is not None and value < previous - _NEW_YEAR_GAP:
                extra_years += 1
                value = value.replace(year=value.year + 1)
            updates[field] = previous = value
        result.append(week.model_copy(update=updates))
    return result
