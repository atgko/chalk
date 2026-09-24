"""Front-matter metadata extraction shared by the Word and markdown
extractors: recognizing "Label: value" lines for course title, number,
section, credits, term, instructor, and meeting pattern.

Both source formats use the same MVP convention. This hasn't been
validated against a real syllabus yet — that happens with the Section 15
test corpus, before the Nov 8 readiness meeting. See PLAN.md's "Word
format variability" risk, which applies equally to markdown.
"""

from __future__ import annotations

import re

from chalk.errors import ExtractionError

_LABELED_LINE_RE = re.compile(r"^([^:]+):\s*(.+)$")

_FIELD_ALIASES = {
    "course": "title",
    "course title": "title",
    "title": "title",
    "course number": "number",
    "number": "number",
    "section": "section",
    "credits": "credits",
    "term": "term",
    "instructor": "instructor",
    "meeting pattern": "meeting_pattern",
    "format": "meeting_pattern",
}

_REQUIRED_FIELDS = {
    "title",
    "number",
    "section",
    "credits",
    "term",
    "instructor",
    "meeting_pattern",
}


def parse_labeled_line(text: str) -> tuple[str, str] | None:
    """If `text` is a "Label: value" line for a recognized field, return
    (field_name, value); otherwise None (an unrecognized label, or no
    label at all)."""
    match = _LABELED_LINE_RE.match(text)
    if not match:
        return None
    field_name = _FIELD_ALIASES.get(match.group(1).strip().lower())
    if not field_name:
        return None
    return field_name, match.group(2).strip()


def finalize_front_matter(raw_fields: dict[str, str]) -> dict:
    """Validate that all required fields were found and coerce `credits`
    to int.

    Raises ExtractionError with a plain-English message if a required
    field is missing or `credits` isn't a whole number.
    """
    missing = _REQUIRED_FIELDS - raw_fields.keys()
    if missing:
        raise ExtractionError(
            "Could not find the following syllabus details near the top of "
            f"the document: {', '.join(sorted(missing))}. Make sure each is "
            "on its own line, formatted like 'Term: Fall 2026'."
        )

    try:
        raw_fields["credits"] = int(raw_fields["credits"])
    except ValueError as exc:
        raise ExtractionError(
            f"Could not read 'Credits: {raw_fields['credits']}' as a whole number."
        ) from exc

    return raw_fields
