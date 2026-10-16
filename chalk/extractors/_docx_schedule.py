"""Word schedule-table reading shared by the extractor and the rollover
writer: week labels, locating the schedule (possibly split across several
tables), classifying rows, and turning week rows into Week objects.

Real syllabi vary more than the MVP convention assumed (teammate testing,
Sept 2026): labels like "Week 1 (Jan. 6)" as well as "Week 1 (8/24)",
text after the label ("Week 14 (Apr. 7) – Final Presentations"), one table
per module with title and header rows, and a separate "Assignment Due"
column. Both the extractor and docx_rollover use these helpers, so a row
the extractor reads as a week or a break is the row the writer rewrites.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass

from chalk.errors import AmbiguousTableError, ExtractionError
from chalk.extractors._dates import DATE_RANGE_RE
from chalk.models import Week

# "Week 1 (8/24)", "Week 12 (12/1)", "Week 1 (Jan. 6)", "Week 3 (September 8)".
WEEK_LABEL_RE = re.compile(
    r"week\s*(\d+)\s*\(\s*(?:(\d{1,2})/(\d{1,2})|([a-z]{3,9})(\.?)\s*(\d{1,2}))\s*\)",
    re.IGNORECASE,
)
_MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_abbr) if name}
_LABEL_SUFFIX_EDGE = " \t–—-:|"
_DUE_RE = re.compile(r"\bdue\b", re.IGNORECASE)
_NOTE_PREFIX_RE = re.compile(r"^notes?:\s*", re.IGNORECASE)
_ASSIGNMENT_COLUMN_RE = re.compile(r"^(assignments?|deliverables?)\b|\bdue\b", re.IGNORECASE)


@dataclass(frozen=True)
class WeekLabel:
    week_number: int
    month: int
    day: int
    start: int  # span of the label within the text it was found in
    end: int
    month_style: str  # "numeric", "abbr", or "full"
    has_period: bool = False


def parse_week_label(text: str) -> WeekLabel | None:
    """The first "Week N (date)" label in `text`, or None."""
    for match in WEEK_LABEL_RE.finditer(text):
        week_number = int(match.group(1))
        if match.group(2):
            return WeekLabel(
                week_number,
                int(match.group(2)),
                int(match.group(3)),
                match.start(),
                match.end(),
                "numeric",
            )
        month_name = match.group(4)
        month = _MONTHS.get(month_name[:3].lower())
        if month is None:
            continue  # e.g. "Week 3 (Online 2)" — not a date
        style = "abbr" if len(month_name) <= 4 or match.group(5) else "full"
        return WeekLabel(
            week_number,
            month,
            int(match.group(6)),
            match.start(),
            match.end(),
            style,
            bool(match.group(5)),
        )
    return None


def format_week_label(week_number: int, date: dt.date, like: WeekLabel | None = None) -> str:
    """ "Week N (date)", writing the date the way `like` did (default M/D)."""
    if like is None or like.month_style == "numeric":
        date_text = f"{date.month}/{date.day}"
    elif like.month_style == "abbr":
        date_text = f"{calendar.month_abbr[date.month]}{'.' if like.has_period else ''} {date.day}"
    else:
        date_text = f"{calendar.month_name[date.month]} {date.day}"
    return f"Week {week_number} ({date_text})"


# ---- Locating the schedule ----------------------------------------------


def looks_like_schedule_table(table) -> bool:
    # Skip row 0 (assumed header) — at least one data row's first cell
    # must hold a week label.
    return any(parse_week_label(row.cells[0].text) for row in table.rows[1:])


def find_schedule_tables(document, table_index: int | None = None) -> list:
    """The schedule's table(s). Several candidate tables whose week numbers
    continue one another (Weeks 1-3, then 4-6, ...) are one schedule split
    by module; otherwise more than one candidate is genuinely ambiguous.
    `table_index` picks one candidate (DECISIONS.md manual override)."""
    candidates = [table for table in document.tables if looks_like_schedule_table(table)]

    if table_index is not None:
        if not 0 <= table_index < len(candidates):
            raise ExtractionError(
                "That table choice is no longer valid. Upload the syllabus again and pick a table."
            )
        return [candidates[table_index]]
    if len(candidates) == 1 or (candidates and _weeks_continue_across(candidates)):
        return candidates
    if not candidates:
        raise AmbiguousTableError(
            "No schedule table found. Make sure your syllabus has a table "
            "with 'Week' in the first column, then try again.",
            candidates=[],
        )
    raise AmbiguousTableError(
        "Multiple possible schedule tables were found. Choose the correct one below.",
        candidates=[_table_preview(table) for table in candidates],
    )


def _weeks_continue_across(tables) -> bool:
    previous_max = 0
    for table in tables:
        numbers = [
            label.week_number
            for row in table.rows
            if (label := parse_week_label(row.cells[0].text))
        ]
        if min(numbers) <= previous_max:
            return False
        previous_max = max(numbers)
    return True


def _table_preview(table) -> str:
    # Header plus the first data row: two schedule-like tables often share
    # an identical header, so the header alone can't tell them apart.
    return " / ".join(" | ".join(cell.text for cell in row.cells) for row in table.rows[:2])


# ---- Rows -----------------------------------------------------------------


def classify_row(row) -> str:
    """ "week" (has a week label), "break" (a dated row like "Fall Break
    (10/10 - 10/18)"), or "other" (a header or module-title row, skipped).
    Raises ExtractionError for an undated row that names a break — its
    dates can't be guessed."""
    label_text = row.cells[0].text.strip()
    if parse_week_label(label_text):
        return "week"
    if DATE_RANGE_RE.search(_break_text(row)):
        return "break"
    if "break" in label_text.lower():
        raise ExtractionError(
            f"Could not determine the dates for the break row '{label_text}'. "
            "Include a date range like '(10/10 - 10/18)' next to the label."
        )
    return "other"


def _break_text(row) -> str:
    second = row.cells[1].text if len(row.cells) > 1 else ""
    return f"{row.cells[0].text} {second}"


def extract_weeks(tables, year: int) -> list[Week]:
    weeks: list[Week] = []
    for table in tables:
        assignment_columns = _assignment_columns(table)
        for row in table.rows[1:]:  # row 0 is a header
            kind = classify_row(row)
            if kind == "week":
                weeks.append(_build_regular_week(row, assignment_columns, year))
            elif kind == "break":
                weeks.append(_build_break_week(row, year))
    if not weeks:  # pragma: no cover - a schedule table always has a week row
        raise ExtractionError(
            "The schedule table was found but contains no week rows. Make "
            "sure it has at least one row below the header."
        )
    return weeks


def _assignment_columns(table) -> set[int]:
    """Columns whose header reads like "Assignment Due" — everything in
    them is an assignment. The header is the last non-week row before the
    first week row (a module table may have a title row above it)."""
    header = None
    for row in table.rows:
        if parse_week_label(row.cells[0].text):
            break
        header = row
    if header is None:  # pragma: no cover - looks_like_schedule_table skips row 0
        return set()
    return {
        i
        for i, cell in enumerate(header.cells)
        if i > 0 and _ASSIGNMENT_COLUMN_RE.search(cell.text.strip())
    }


def _build_regular_week(row, assignment_columns: set[int], year: int) -> Week:
    label_paragraph, *other_paragraphs = [p.text.strip() for p in row.cells[0].paragraphs] or [""]
    label = parse_week_label(label_paragraph)
    first_cell_lines = [label_paragraph[label.end :].strip(_LABEL_SUFFIX_EDGE)] + other_paragraphs
    topics, assignments, notes = _classify_lines([line for line in first_cell_lines if line])

    for index, cell in enumerate(_distinct_cells(row)[1:], start=1):
        lines = cell_lines(cell)
        if index in assignment_columns:
            more_topics, more_assignments, more_notes = [], *_split_notes(lines)
        else:
            more_topics, more_assignments, more_notes = _classify_lines(lines)
        topics += more_topics
        assignments += more_assignments
        notes = " ".join(part for part in (notes, more_notes) if part) or None

    return Week(
        week_number=label.week_number,
        date=dt.date(year, label.month, label.day),
        label=row.cells[0].text.strip(),
        is_break=False,
        topics=topics,
        assignments=assignments,
        notes=notes,
    )


def _build_break_week(row, year: int) -> Week:
    m1, d1, m2, d2 = (int(group) for group in DATE_RANGE_RE.search(_break_text(row)).groups())
    return Week(
        week_number=None,
        date_start=dt.date(year, m1, d1),
        date_end=dt.date(year, m2, d2),
        label=row.cells[0].text.strip(),
        is_break=True,
    )


def _distinct_cells(row) -> list:
    """A row's cells with horizontally merged duplicates removed."""
    seen, cells = set(), []
    for cell in row.cells:
        if id(cell._tc) not in seen:
            seen.add(id(cell._tc))
            cells.append(cell)
    return cells


def cell_lines(cell) -> list[str]:
    return [text for p in cell.paragraphs if (text := p.text.strip())]


def _classify_lines(lines: list[str]) -> tuple[list[str], list[str], str | None]:
    """Split a schedule cell's lines into topics, assignments, and an
    optional notes string.

    MVP heuristic: a line explicitly prefixed "Note:"/"Notes:" becomes
    part of the week's notes; a line containing the word "due" is an
    assignment; everything else is a topic.
    """
    topics: list[str] = []
    other: list[str] = []
    for line in lines:
        (other if _NOTE_PREFIX_RE.match(line) or _DUE_RE.search(line) else topics).append(line)
    assignments, notes = _split_notes(other)
    return topics, assignments, notes


def _split_notes(lines: list[str]) -> tuple[list[str], str | None]:
    """(assignment lines, notes) — "Note:" lines become the notes."""
    assignments, notes_parts = [], []
    for line in lines:
        note_match = _NOTE_PREFIX_RE.match(line)
        if note_match:
            notes_parts.append(line[note_match.end() :].strip())
        else:
            assignments.append(line)
    return assignments, " ".join(notes_parts) or None
