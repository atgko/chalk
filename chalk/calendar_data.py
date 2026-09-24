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


def suggest_target_term(current_term: str, term_names: list[str]) -> str | None:
    """Default rollover target: the same season one year later (Fall 2026
    -> Fall 2027) if the calendar has it, else the first listed term after
    the current one, else None."""
    parts = current_term.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit():
        same_season_next_year = f"{parts[0]} {int(parts[1]) + 1}"
        if same_season_next_year in term_names:
            return same_season_next_year
    if current_term in term_names:
        index = term_names.index(current_term)
        if index + 1 < len(term_names):
            return term_names[index + 1]
    return None
