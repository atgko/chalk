"""Markdown (.md) rollover writer (F-02, markdown path).

Unlike the Word writer, this regenerates the schedule table wholesale
from a rolled-over CourseData's weeks rather than patching individual
cells — markdown's single-cell-per-column format (PRD section 6.1: one
Topic, one Major Work per row) means "regenerate the table" and "update
only the date columns" produce an identical result, since topics and
assignments are carried over unchanged from extraction either way. Only
the schedule table's own lines are replaced; everything else in the file
(front matter, other tables, prose) is preserved untouched. The front-
matter Term: line and any matching university-dates rows are also
updated, mirroring the Word writer.

DST-boundary flags (PRD section 6.2, markdown-only) are computed by
chalk.rollover.preview.roll_over_course() and surfaced to the instructor
in the Rollover Preview — this writer never embeds them in the file or
auto-applies a timezone suffix.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from chalk.archiving import archive_before_write
from chalk.extractors._front_matter import parse_labeled_line
from chalk.models import CourseData, UniversityDate
from chalk.rollover.preview import break_name

_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")


def write_rolled_over_markdown(
    source_md_path,
    new_course_data: CourseData,
    output_path,
    *,
    eval_log_path=None,
) -> None:
    """Write the rolled-over schedule into a fresh copy of the original
    markdown file at `output_path`, archiving whatever was already there
    first."""
    lines = Path(source_md_path).read_text(encoding="utf-8").splitlines()

    lines = _replace_term_line(lines, new_course_data.course.term)
    lines = _replace_schedule_table(lines, new_course_data)
    lines = _replace_university_dates_table(lines, new_course_data.university_dates)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    archive_before_write(output_path, eval_log_path=eval_log_path)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _replace_term_line(lines: list[str], new_term: str) -> list[str]:
    result = list(lines)
    for i, line in enumerate(result):
        stripped = line.strip()
        if not stripped:  # pragma: no cover - none of our fixtures put a blank line before Term
            continue
        parsed = parse_labeled_line(stripped)
        if parsed and parsed[0] == "term":
            result[i] = f"Term: {new_term}"
            return result
    return result  # pragma: no cover - front matter is required, so Term is always found


def _replace_schedule_table(lines: list[str], new_course_data: CourseData) -> list[str]:
    table_range = _find_table_line_range(lines, lambda header: header[0].strip().lower() == "week")
    if table_range is None:  # pragma: no cover - extraction already guaranteed one exists
        return lines

    start, end = table_range
    return lines[:start] + _render_schedule_table(new_course_data) + lines[end:]


def _render_schedule_table(new_course_data: CourseData) -> list[str]:
    rows = ["| Week | Dates | Topic | Major Work |", "| --- | --- | --- | --- |"]
    for week in sorted(new_course_data.weeks, key=lambda w: w.date or w.date_start):
        if week.is_break:
            rows.append(
                f"| - | {week.date_start.month}/{week.date_start.day} - "
                f"{week.date_end.month}/{week.date_end.day} | {break_name(week.label)} |  |"
            )
        else:
            # Regular weeks need a full M/D - M/D range, not a single
            # date -- that's what the markdown format's Dates column (and
            # the extractor's DATE_RANGE_RE) actually expects; a 7-day
            # week spans its start date through 6 days later.
            week_end = week.date + dt.timedelta(days=6)
            topic = "; ".join(week.topics)
            major_work = "; ".join(week.assignments)
            rows.append(
                f"| {week.week_number} | {week.date.month}/{week.date.day} - "
                f"{week_end.month}/{week_end.day} | {topic} | {major_work} |"
            )
    return rows


def _replace_university_dates_table(
    lines: list[str], university_dates: list[UniversityDate]
) -> list[str]:
    table_range = _find_table_line_range(
        lines,
        lambda header: "event" in [c.lower() for c in header] and "date" in [c.lower() for c in header],
    )
    if table_range is None:
        return lines

    start, end = table_range
    original_block = lines[start:end]
    new_block = original_block[:2]  # header + separator, unchanged
    dates_by_event = {entry.event: entry for entry in university_dates}

    for line in original_block[2:]:
        cells = _split_table_row(line)
        entry = dates_by_event.get(cells[0]) if cells else None
        if entry is None:
            new_block.append(line)
            continue
        new_block.append(f"| {cells[0]} | {_format_university_date(entry)} |")

    return lines[:start] + new_block + lines[end:]


def _format_university_date(entry: UniversityDate) -> str:
    if entry.date is not None:
        return f"{entry.date.month}/{entry.date.day}/{entry.date.year}"
    return f"{entry.date_start.month}/{entry.date_start.day} - {entry.date_end.month}/{entry.date_end.day}"


# ---- Small line-range table locator (distinct from markdown_extractor's
# in-memory table parser: this one needs line *positions* so a table's
# lines can be sliced out and replaced, not just its cell content). ------


def _find_table_line_range(lines: list[str], header_predicate) -> tuple[int, int] | None:
    start = None
    for i, line in enumerate(lines):
        is_table_line = line.strip().startswith("|") and line.strip().endswith("|")
        if is_table_line and start is None:
            start = i
        elif not is_table_line and start is not None:
            if _block_matches(lines[start:i], header_predicate):
                return start, i
            start = None
    if start is not None and _block_matches(lines[start:], header_predicate):
        return start, len(lines)
    return None


def _block_matches(block_lines: list[str], header_predicate) -> bool:
    rows = [_split_table_row(line) for line in block_lines]
    data_rows = [row for row in rows if not _is_separator_row(row)]
    return bool(data_rows) and header_predicate(data_rows[0])


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL_RE.match(cell) for cell in cells)
