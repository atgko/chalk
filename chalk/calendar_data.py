"""Academic calendar data loading and term lookup (PRD section 5.3).

University of Utah only for the MVP. Graceful degradation is the whole
point of `find_term`: a term missing from the data file is not an error —
callers fall back to asking the instructor for a Week 1 date directly
(PRD section 5.3: "It never fails hard on a missing term.").
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_calendars(path: Path) -> dict[str, Any]:
    """Load the calendars.json file.

    A malformed or missing file raises a plain `OSError`/`json.JSONDecodeError`
    — that's a packaging/config problem the instructor can't fix by
    reformatting a syllabus, so it isn't wrapped in a Chalk-specific error.
    """
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_term(calendars: dict[str, Any], term_name: str) -> dict[str, Any] | None:
    """Look up a term by exact name (e.g. "Fall 2027") in loaded calendars
    data.

    Returns None when the term isn't found. Callers must treat that as
    "prompt the instructor for a Week 1 date and continue," never as a
    hard failure — see PRD section 5.3.
    """
    for term in calendars.get("terms", []):
        if term.get("term") == term_name:
            return term
    return None
