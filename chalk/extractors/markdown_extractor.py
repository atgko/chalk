"""Markdown (.md) syllabus extraction (F-01, markdown path).

Parses the schedule table (headers "| Week | Dates | Topic | Major Work
|"), detects break rows (week cell literally "-"), and reads front-matter
metadata using the same "Label: value" line convention as the Word path.

The PRD's markdown-path bullet list (section 6.1) only requires the
schedule table and university dates. This extractor also looks for
learning objectives and an assessments table opportunistically, so a
markdown syllabus that happens to have them isn't left with empty
course.json sections — but unlike the schedule table and front matter,
their absence is never an error for this format.

Uses only the standard library plus regex for table parsing (PRD section
4: "No heavy dependency needed for structured tables").
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from chalk.errors import AmbiguousTableError, ExtractionError
from chalk.extractors._dates import DATE_RANGE_RE, FULL_DATE_RE, year_from_term
from chalk.extractors._front_matter import finalize_front_matter, parse_labeled_line
from chalk.models import Assessment, CourseData, CourseInfo, UniversityDate, Week

_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
_HEADING_PREFIX_RE = re.compile(r"^#+\s*(.+)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.+)$")
_WEIGHT_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")

_OBJECTIVES_HEADINGS = {"learning objectives", "course outcome and objectives"}

Table = list[list[str]]


def extract_course_data(md_path, *, schedule_table_index: int | None = None) -> CourseData:
    """Parse a markdown syllabus into a CourseData object.

    Raises AmbiguousTableError if zero or multiple candidate schedule
    tables are found, or ExtractionError for any other recognized parsing
    failure. Never writes to md_path. `schedule_table_index` works as in
    the Word extractor.
    """
    try:
        text = Path(md_path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ExtractionError(
            "This file doesn't look like a plain-text markdown file. Make "
            "sure it's saved as UTF-8 text."
        ) from exc

    front_matter = _extract_front_matter(text)
    year = _year_from_term_or_raise(front_matter["term"])

    tables = _parse_markdown_tables(text)
    schedule_table = _find_schedule_table(tables, schedule_table_index)
    weeks = _extract_weeks(schedule_table, year)

    course_info = CourseInfo(
        title=front_matter["title"],
        number=front_matter["number"],
        section=front_matter["section"],
        credits=front_matter["credits"],
        term=front_matter["term"],
        term_start=_course_start_date(weeks),
        term_end=_course_end_date(weeks),
        duration_weeks=sum(1 for week in weeks if not week.is_break),
        meeting_pattern=front_matter["meeting_pattern"],
        instructor=front_matter["instructor"],
        source_format="markdown",
        source_file=str(md_path),
        extracted_at=dt.datetime.now(dt.timezone.utc),
    )

    return CourseData(
        course=course_info,
        learning_objectives=_extract_learning_objectives(text),
        assessments=_extract_assessments(tables),
        weeks=weeks,
        university_dates=_extract_university_dates(tables, year),
    )


# ---- Front matter ----------------------------------------------------------


def _extract_front_matter(text: str) -> dict:
    raw_fields: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|"):
            continue
        parsed = parse_labeled_line(stripped)
        if parsed:
            field_name, value = parsed
            if field_name not in raw_fields:
                raw_fields[field_name] = value
    return finalize_front_matter(raw_fields)


def _year_from_term_or_raise(term: str) -> int:
    year = year_from_term(term)
    if year is None:
        raise ExtractionError(f"Could not determine the academic year from the term '{term}'.")
    return year


# ---- Markdown table parsing -------------------------------------------------


def _parse_markdown_tables(text: str) -> list[Table]:
    """Return every markdown table in `text`: a list of tables, each a
    list of rows, each row a list of stripped cell strings. The
    "|---|---|" separator row is dropped, so a table's first remaining
    row is its header."""
    tables: list[Table] = []
    current: Table = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1:
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if _is_separator_row(cells):
                continue
            current.append(cells)
        elif current:
            tables.append(current)
            current = []

    if current:
        tables.append(current)
    return tables


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL_RE.match(cell) for cell in cells)


def _find_schedule_table(tables: list[Table], table_index: int | None = None) -> Table:
    candidates = [table for table in tables if len(table) >= 2 and table[0][0].strip().lower() == "week"]

    if table_index is not None:
        if not 0 <= table_index < len(candidates):
            raise ExtractionError(
                "That table choice is no longer valid. Upload the syllabus again and pick a table."
            )
        return candidates[table_index]

    if len(candidates) == 1:
        return candidates[0]

    if not candidates:
        raise AmbiguousTableError(
            "No schedule table found. Make sure your syllabus has a table "
            "with 'Week' in the first column, then try again.",
            candidates=[],
        )

    raise AmbiguousTableError(
        "Multiple possible schedule tables were found. Choose the correct one below.",
        candidates=[" / ".join(" | ".join(row) for row in table[:2]) for table in candidates],
    )


# ---- Schedule weeks ---------------------------------------------------------


def _extract_weeks(table: Table, year: int) -> list[Week]:
    weeks: list[Week] = []
    for row in table[1:]:  # skip header
        week_cell = row[0].strip() if len(row) > 0 else ""
        dates_cell = row[1].strip() if len(row) > 1 else ""
        topic_cell = row[2].strip() if len(row) > 2 else ""
        major_work_cell = row[3].strip() if len(row) > 3 else ""

        if week_cell == "-":
            weeks.append(_build_break_week(dates_cell, topic_cell, year))
        else:
            weeks.append(_build_regular_week(week_cell, dates_cell, topic_cell, major_work_cell, year))

    if not weeks:  # pragma: no cover - _find_schedule_table already guarantees >=1 data row
        raise ExtractionError(
            "The schedule table was found but contains no week rows. Make "
            "sure it has at least one row below the header."
        )
    return weeks


def _build_regular_week(
    week_cell: str, dates_cell: str, topic_cell: str, major_work_cell: str, year: int
) -> Week:
    try:
        week_number = int(week_cell)
    except ValueError as exc:
        raise ExtractionError(
            f"Could not read '{week_cell}' as a week number in the schedule table."
        ) from exc

    week_date = _first_date_in_range(dates_cell, year)
    if week_date is None:
        raise ExtractionError(
            f"Could not determine the date for week {week_number}. Include a "
            "date range like '8/24 - 8/30' in the Dates column."
        )

    return Week(
        week_number=week_number,
        date=week_date,
        label=f"Week {week_number}",
        is_break=False,
        topics=[topic_cell] if topic_cell else [],
        assignments=[major_work_cell] if major_work_cell else [],
    )


def _build_break_week(dates_cell: str, topic_cell: str, year: int) -> Week:
    range_match = DATE_RANGE_RE.search(dates_cell)
    if not range_match:
        raise ExtractionError(
            "Could not determine the dates for a break row. Include a date "
            "range like '10/10 - 10/18' in the Dates column."
        )
    m1, d1, m2, d2 = (int(group) for group in range_match.groups())
    return Week(
        week_number=None,
        date_start=dt.date(year, m1, d1),
        date_end=dt.date(year, m2, d2),
        label=topic_cell or "Break",
        is_break=True,
        topics=[],
        assignments=[],
    )


def _first_date_in_range(text: str, year: int) -> dt.date | None:
    match = DATE_RANGE_RE.search(text)
    if not match:
        return None
    month, day = int(match.group(1)), int(match.group(2))
    return dt.date(year, month, day)


def _course_start_date(weeks: list[Week]) -> dt.date:
    first = weeks[0]
    return first.date if first.date is not None else first.date_start


def _course_end_date(weeks: list[Week]) -> dt.date:
    last = weeks[-1]
    return last.date if last.date is not None else last.date_end


# ---- Learning objectives (opportunistic) -----------------------------------


def _extract_learning_objectives(text: str) -> list[str]:
    objectives: list[str] = []
    collecting = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        heading_match = _HEADING_PREFIX_RE.match(stripped)
        heading_text = (heading_match.group(1) if heading_match else stripped).strip().lower()

        if heading_text.rstrip(":") in _OBJECTIVES_HEADINGS:
            collecting = True
            continue

        if not collecting:
            continue

        if heading_match or stripped.startswith("|"):
            break  # a new heading or table ends the objectives list

        bullet_match = _BULLET_RE.match(stripped)
        if not bullet_match:
            break
        objectives.append(bullet_match.group(1).strip())

    return objectives


# ---- Assessments table (opportunistic) -------------------------------------


def _extract_assessments(tables: list[Table]) -> list[Assessment]:
    for table in tables:
        header = [cell.lower() for cell in table[0]]
        if "assessment" in header and any("weight" in cell for cell in header):
            return _parse_assessment_rows(table)
    return []


def _parse_assessment_rows(table: Table) -> list[Assessment]:
    assessments = []
    for row in table[1:]:
        name = row[0].strip()
        weight_text = row[1] if len(row) > 1 else ""
        weight_match = _WEIGHT_PERCENT_RE.search(weight_text)
        if not weight_match:
            continue
        assessments.append(Assessment(name=name, weight=float(weight_match.group(1)) / 100))
    return assessments


# ---- University dates table (opportunistic) --------------------------------


def _extract_university_dates(tables: list[Table], year: int) -> list[UniversityDate]:
    for table in tables:
        header = [cell.lower() for cell in table[0]]
        if "event" in header and "date" in header:
            return _parse_university_date_rows(table, year)
    return []


def _parse_university_date_rows(table: Table, year: int) -> list[UniversityDate]:
    dates = []
    for row in table[1:]:
        event = row[0].strip()
        date_text = row[1].strip() if len(row) > 1 else ""

        range_match = DATE_RANGE_RE.search(date_text)
        if range_match:
            m1, d1, m2, d2 = (int(group) for group in range_match.groups())
            dates.append(
                UniversityDate(
                    event=event, date_start=dt.date(year, m1, d1), date_end=dt.date(year, m2, d2)
                )
            )
            continue

        full_match = FULL_DATE_RE.search(date_text)
        if full_match:
            month, day, full_year = (int(group) for group in full_match.groups())
            dates.append(UniversityDate(event=event, date=dt.date(full_year, month, day)))

    return dates
