"""Small date-parsing primitives shared by the Word and markdown
extractors. Each extractor wraps these with its own error messages —
what's shared here is just the regex/parsing logic, not the fail-loud
behavior, since the two formats surface errors in slightly different
contexts.
"""

from __future__ import annotations

import re

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
