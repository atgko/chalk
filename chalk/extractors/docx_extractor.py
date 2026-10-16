"""Word (.docx) syllabus extraction (F-01, Word path).

Locates the schedule table by the "Week N (M/DD)" heuristic in its first
column, reads front-matter metadata loosely (chalk.extractors._front_matter:
label lines, two-column tables, or guesses from the title lines), learning objectives from a bulleted list under one
of two known headings, assessments from a two-column weight table, and
university dates from an optional two-column dates table.

Never writes to the source document — it is only ever opened for reading
(PRD section 6.1: "Do not modify any part of the document during
extraction").

The front-matter and cell-classification heuristics below are an MVP
convention, not something the PRD specifies precisely — they haven't yet
been validated against a real syllabus (that happens with the Section 15
test corpus, before the Nov 8 readiness meeting). See PLAN.md's "Word
format variability" risk.
"""

from __future__ import annotations

import datetime as dt
import re
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from chalk.errors import ExtractionError, ProtectedFileError
from chalk.extractors._dates import DATE_RANGE_RE, FULL_DATE_RE, year_from_term
from chalk.extractors._docx_schedule import extract_weeks, find_schedule_tables
from chalk.extractors._front_matter import extract_front_matter
from chalk.models import Assessment, CourseData, CourseInfo, UniversityDate, Week

_WEIGHT_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_WEIGHT_HEADER_RE = re.compile(r"weight|percent|%", re.IGNORECASE)

_OBJECTIVES_HEADINGS = {"learning objectives", "course outcome and objectives"}
# An all-caps line this short ("REQUIRED TEXT AND COURSE MATERIALS") is a
# section heading typed in Normal style, which ends the objectives list.
_CAPS_HEADING_MAX_CHARS = 60


def extract_course_data(docx_path, *, schedule_table_index: int | None = None) -> CourseData:
    """Parse a Word syllabus into a CourseData object.

    Raises ProtectedFileError if the file can't be opened at all (usually
    password protection), AmbiguousTableError if zero or multiple
    candidate schedule tables are found, or ExtractionError for any other
    recognized parsing failure. Never writes to docx_path.

    `schedule_table_index` picks one of the candidate tables an earlier
    AmbiguousTableError listed (DECISIONS.md manual override), by position
    in its `candidates` list.
    """
    try:
        document = Document(str(docx_path))
    except (PackageNotFoundError, BadZipFile) as exc:
        raise ProtectedFileError(
            "This Word file is protected. Remove the password in Word "
            "(Review > Protect Document) and re-upload."
        ) from exc

    front_matter = _extract_front_matter(document)
    year = _year_from_term_or_raise(front_matter["term"])

    schedule_tables = find_schedule_tables(document, schedule_table_index)
    weeks = extract_weeks(schedule_tables, year)

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
        source_format="word",
        source_file=str(docx_path),
        extracted_at=dt.datetime.now(dt.UTC),
    )

    return CourseData(
        course=course_info,
        learning_objectives=_extract_learning_objectives(document),
        assessments=_extract_assessments(document),
        weeks=weeks,
        university_dates=_extract_university_dates(document, year),
    )


# ---- Front matter --------------------------------------------------------


def _extract_front_matter(document) -> dict:
    slots = list(front_matter_slots(document))
    return extract_front_matter(
        [slot[1] for slot in slots], header_lines=[slot[2] for slot in slots]
    )


def front_matter_slots(document):
    """(paragraph, text for "Label: value" matching, text for header
    guessing) for every paragraph in reading order, including text inside
    tables — many syllabi put course info in a table at the top. Table
    text is never used for header guessing (a schedule header isn't a
    title). A two-cell row also yields its value cell's paragraph matched
    as "left: right", so a "Term | Fall 2026" row reads like a label line.
    Shared with docx_rollover, which rewrites the term in place."""
    for block in document.iter_inner_content():
        if not hasattr(block, "rows"):
            yield block, block.text, block.text
            continue
        for row in block.rows:
            cells = row.cells
            if len(cells) == 2:
                label = cells[0].text.strip().rstrip(":")
                yield cells[1].paragraphs[0], f"{label}: {cells[1].text.strip()}", ""
            for cell in cells:
                for paragraph in cell.paragraphs:
                    yield paragraph, paragraph.text, ""


def _year_from_term_or_raise(term: str) -> int:
    year = year_from_term(term)
    if year is None:
        raise ExtractionError(f"Could not determine the academic year from the term '{term}'.")
    return year


# ---- Schedule dates -------------------------------------------------------


def _course_start_date(weeks: list[Week]) -> dt.date:
    first = weeks[0]
    return first.date if first.date is not None else first.date_start


def _course_end_date(weeks: list[Week]) -> dt.date:
    last = weeks[-1]
    return last.date if last.date is not None else last.date_end


# ---- Learning objectives --------------------------------------------------


def _extract_learning_objectives(document) -> list[str]:
    """Paragraphs after a "Learning Objectives" heading, skipping a lead-in
    line ("By the end of this course, you will be able to:") and stopping
    at the next heading — a Heading style or an all-caps Normal line."""
    objectives: list[str] = []
    collecting = False
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if text.lower().rstrip(":") in _OBJECTIVES_HEADINGS:
            collecting = True
            continue
        if not collecting:
            continue
        if _is_heading(paragraph, text):
            break
        if not objectives and text.endswith(":"):
            continue
        objectives.append(text)
    return objectives


def _is_heading(paragraph, text: str) -> bool:
    if paragraph.style is not None and paragraph.style.name.startswith("Heading"):
        return True
    return text.isupper() and len(text) <= _CAPS_HEADING_MAX_CHARS


# ---- Assessments table -----------------------------------------------------


def _extract_assessments(document) -> list[Assessment]:
    """The first table that reads as grading weights: a header with a
    "Weight" (or "%") column, or — with no header row — a table whose
    rows' second cells are mostly percentages. A "Total" row is skipped."""
    for table in document.tables:
        rows = [row for row in table.rows if len(row.cells) >= 2]
        if len(rows) < 2:
            continue
        header_cells = [cell.text.strip() for cell in rows[0].cells[1:]]
        if any(
            _WEIGHT_HEADER_RE.search(cell) and not _WEIGHT_PERCENT_RE.search(cell)
            for cell in header_cells
        ):
            return _parse_assessment_rows(rows[1:])
        weighted = [row for row in rows if _WEIGHT_PERCENT_RE.search(row.cells[1].text)]
        if len(weighted) * 2 > len(rows) and _WEIGHT_PERCENT_RE.search(rows[0].cells[1].text):
            return _parse_assessment_rows(rows)
    return []


def _parse_assessment_rows(rows) -> list[Assessment]:
    assessments = []
    for row in rows:
        name = row.cells[0].text.strip()
        weight_match = _WEIGHT_PERCENT_RE.search(row.cells[1].text)
        if not weight_match or name.lower().startswith("total"):
            continue
        assessments.append(Assessment(name=name, weight=float(weight_match.group(1)) / 100))
    return assessments


# ---- University dates table ------------------------------------------------


def _extract_university_dates(document, year: int) -> list[UniversityDate]:
    for table in document.tables:
        if not table.rows:  # pragma: no cover - python-docx tables always have >=1 row
            continue
        header = [cell.text.strip().lower() for cell in table.rows[0].cells]
        if "event" in header and "date" in header:
            return _parse_university_date_rows(table, year)
    return []


def _parse_university_date_rows(table, year: int) -> list[UniversityDate]:
    dates = []
    for row in table.rows[1:]:
        event = row.cells[0].text.strip()
        date_text = row.cells[1].text.strip()

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
