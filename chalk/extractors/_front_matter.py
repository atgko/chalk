"""Front-matter metadata extraction shared by the Word and markdown
extractors: course title, number, section, credits, term, instructor, and
meeting pattern.

Two passes over the document's lines (in reading order):
1. "Label: value" lines, accepting the common label variants real syllabi
   use ("Professor:", "Semester:", "Credit Hours:", ...).
2. For title, number, and term still missing, guesses from the header —
   the first few non-empty lines — e.g. "Networking and Servers – Online
   Fall 2026" followed by "IS 6640, 10-week ...".

Only the term is required (rollover and the date parser need its year);
the title falls back to the course number. Everything else is optional
and left blank for the instructor to fill in on the Review tab — a real
syllabus rarely labels all seven fields (teammate feedback, Sept 2026).
"""

from __future__ import annotations

import re

from chalk.errors import ExtractionError

_LABELED_LINE_RE = re.compile(r"^([^:]+):\s*(.+)$")
_MARKUP_CHARS = "*_#> \t"

# How many non-empty lines from the top count as the header for guessing.
_HEADER_LINE_COUNT = 15

_SEASON_YEAR_RE = re.compile(
    r"\b(fall|spring|summer)\s+(?:semester\s+|term\s+)?(\d{4})\b", re.IGNORECASE
)
_COURSE_NUMBER_RE = re.compile(r"\b(?!(?:FALL|SPRING|SUMMER)\b)([A-Z]{2,5})[ -]?(\d{4})\b")
_FIRST_INTEGER_RE = re.compile(r"\d+")
_CREDITS_RE = re.compile(r"\b(\d{1,2})\s+credit(?:\s+hours?)?\b", re.IGNORECASE)
_MEETING_RE = re.compile(
    r"\b(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)(?:day)?s?\b.*\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
    re.IGNORECASE,
)
# A "Label:" with no digits ("Office Hours:") — such a line is about
# something else, so it's never used for a meeting-pattern guess.
_ANY_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z /&#'-]{0,40}:")
_TITLE_NOISE_RE = re.compile(r"\bsyllabus\b", re.IGNORECASE)
_TITLE_EDGE_CHARS = " \t-–—:,|·"

_FIELD_ALIASES = {
    "course": "title",
    "course title": "title",
    "course name": "title",
    "title": "title",
    "course number": "number",
    "course code": "number",
    "course #": "number",
    "number": "number",
    "section": "section",
    "section number": "section",
    "credits": "credits",
    "credit hours": "credits",
    "credit": "credits",
    "units": "credits",
    "term": "term",
    "semester": "term",
    "instructor": "instructor",
    "instructor name": "instructor",
    "professor": "instructor",
    "professors": "instructor",
    "instructors": "instructor",
    "faculty": "instructor",
    "meeting pattern": "meeting_pattern",
    "meeting time": "meeting_pattern",
    "meeting times": "meeting_pattern",
    "meeting days": "meeting_pattern",
    "class meetings": "meeting_pattern",
    "class time": "meeting_pattern",
    "class times": "meeting_pattern",
    "format": "meeting_pattern",
}

_OPTIONAL_TEXT_FIELDS = ("section", "instructor", "meeting_pattern")


def parse_labeled_line(text: str) -> tuple[str, str] | None:
    """If `text` is a "Label: value" line for a recognized field, return
    (field_name, value); otherwise None (an unrecognized label, or no
    label at all). Markdown emphasis around the label ("**Term:**") is
    ignored."""
    match = _LABELED_LINE_RE.match(text.strip())
    if not match:
        return None
    field_name = _FIELD_ALIASES.get(match.group(1).strip(_MARKUP_CHARS).lower())
    value = match.group(2).strip(_MARKUP_CHARS)
    if not field_name or not value:
        return None
    return field_name, value


def extract_front_matter(lines: list[str], *, header_lines: list[str] | None = None) -> dict:
    """Read course metadata from a document's lines (in reading order).

    `header_lines` are the lines eligible for guessing title, number, and
    term (default: `lines`). The extractors pass only body text there, so
    table rows count as "Label: value" lines but never as a title.

    Returns every field; missing optional text fields are "", missing
    credits is None. Raises ExtractionError with a plain-English message
    if no term can be found.
    """
    fields = _labeled_fields(lines)
    candidates = lines if header_lines is None else header_lines
    # A Word paragraph with soft line breaks holds several header lines.
    header = [part.strip() for line in candidates for part in line.split("\n") if part.strip()]
    header = header[:_HEADER_LINE_COUNT]

    fields.setdefault("term", _guess_term(header))
    fields.setdefault("number", _guess_number(header))
    fields.setdefault("title", _guess_title(header))
    fields.setdefault("credits", _guess_credits(header))
    fields.setdefault("meeting_pattern", _guess_meeting_pattern(header))

    if not fields["term"]:
        raise ExtractionError(
            "Could not find the term (for example 'Fall 2026') near the top of the syllabus. "
            "Add a line like 'Term: Fall 2026' and upload it again."
        )
    fields["term"] = _normalize_term(fields["term"])
    fields["number"] = fields["number"] or ""
    fields["title"] = fields["title"] or fields["number"] or "Untitled course"
    fields["credits"] = _parse_credits(fields.get("credits"))
    for name in _OPTIONAL_TEXT_FIELDS:
        if fields.get(name) is None:
            fields[name] = ""
    return fields


def replace_term_text(text: str, new_term: str) -> str | None:
    """Swap the first "Fall 2026"-style term in `text` for `new_term`, or
    None if `text` names no term. Used by the rollover writers when the
    term lives in a title line rather than a "Term:" line."""
    if not _SEASON_YEAR_RE.search(text):
        return None
    return _SEASON_YEAR_RE.sub(new_term, text, count=1)


def term_line_index(lines: list[str], header_lines: list[str]) -> int | None:
    """Where the term was read from, so rollover can rewrite it in place:
    the first labeled term line, else the first header line naming a
    term. `header_lines` is parallel to `lines` ("" where a line isn't
    eligible for header guessing), mirroring extract_front_matter."""
    for index, line in enumerate(lines):
        parsed = parse_labeled_line(line)
        if parsed and parsed[0] == "term":
            return index
    seen = 0
    for index, line in enumerate(header_lines):
        if not line.strip():
            continue
        if _SEASON_YEAR_RE.search(line):
            return index
        seen += 1
        if seen >= _HEADER_LINE_COUNT:
            break
    return None


def _labeled_fields(lines: list[str]) -> dict:
    fields: dict = {}
    for line in lines:
        parsed = parse_labeled_line(line)
        if parsed and parsed[0] not in fields:
            fields[parsed[0]] = parsed[1]
    return fields


def _guess_term(header: list[str]) -> str | None:
    for line in header:
        match = _SEASON_YEAR_RE.search(line)
        if match:
            return match.group(0)
    return None


def _guess_number(header: list[str]) -> str | None:
    for line in header:
        if parse_labeled_line(line):
            continue
        match = _COURSE_NUMBER_RE.search(line)
        if match:
            return f"{match.group(1)} {match.group(2)}"
    return None


def _guess_title(header: list[str]) -> str | None:
    """The first header line that isn't a recognized "Label: value" line,
    with any course number, term, and the word "syllabus" removed."""
    for line in header:
        if parse_labeled_line(line):
            continue
        cleaned = line.strip(_MARKUP_CHARS)
        cleaned = _COURSE_NUMBER_RE.sub("", cleaned, count=1)
        cleaned = _SEASON_YEAR_RE.sub("", cleaned, count=1)
        cleaned = _TITLE_NOISE_RE.sub("", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(_TITLE_EDGE_CHARS)
        if len(cleaned) >= 3:
            return cleaned
    return None


def _guess_credits(header: list[str]) -> str | None:
    for line in header:
        match = _CREDITS_RE.search(line)
        if match:
            return match.group(1)
    return None


def _guess_meeting_pattern(header: list[str]) -> str | None:
    """A header line like "Tuesday 6:00-9:00 pm CRCC 105" (a weekday and a
    time), unless it's labeled as something else ("Office Hours: ...")."""
    for line in header:
        if not _ANY_LABEL_RE.match(line) and _MEETING_RE.search(line):
            return line
    return None


def _normalize_term(term: str) -> str:
    match = _SEASON_YEAR_RE.search(term)
    if not match:
        return term  # e.g. "Fall Semester" — the extractor's year check reports it
    return f"{match.group(1).capitalize()} {match.group(2)}"


def _parse_credits(raw: str | None) -> int | None:
    if raw is None:
        return None
    match = _FIRST_INTEGER_RE.search(raw)
    return int(match.group(0)) if match else None
