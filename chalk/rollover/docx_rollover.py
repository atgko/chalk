"""Word (.docx) rollover writer (F-02, Word path).

Applies a rolled-over CourseData's new dates onto a fresh copy of the
original Word document — mutating each week-label cell's existing run
text in place rather than clearing and rebuilding the paragraph, so
formatting (bold, color, font) survives (python-openxml/python-docx#290;
see PLAN.md Risk #1). All other cell content (topics, assignments, notes)
is left untouched, per PRD section 6.2: "All other cell content
preserved." Quiz/exam/lab numbering embedded in that untouched text is
therefore never renumbered — flagging that for human review is
roll_over_course()'s job (chalk.rollover.preview), not this writer's.

chalk.rollover.preview.roll_over_course() must be called first; this
module only ever applies an already-computed CourseData to a document.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.table import _Row

from chalk.archiving import archive_before_write
from chalk.extractors._dates import DATE_RANGE_RE, FULL_DATE_RE
from chalk.extractors._docx_schedule import (
    classify_row,
    format_week_label,
    looks_like_schedule_table,
    parse_week_label,
)
from chalk.extractors._front_matter import parse_labeled_line, replace_term_text, term_line_index
from chalk.extractors.docx_extractor import front_matter_slots
from chalk.models import CourseData, UniversityDate, Week


def write_rolled_over_docx(
    source_docx_path,
    new_course_data: CourseData,
    output_path,
    *,
    eval_log_path=None,
) -> None:
    """Write the rolled-over schedule into a fresh copy of the original
    Word document at `output_path`, archiving whatever was already there
    first (PRD's "Confirm rollover" step never writes without archiving).
    """
    document = Document(str(source_docx_path))

    _update_front_matter_term(document, new_course_data.course.term)

    new_dates_by_week_number = {
        week.week_number: week.date
        for week in new_course_data.weeks
        if not week.is_break and week.date is not None
    }
    new_break_weeks = [week for week in new_course_data.weeks if week.is_break]

    schedule_tables = [table for table in document.tables if looks_like_schedule_table(table)]
    _update_schedule(schedule_tables, new_dates_by_week_number, new_break_weeks)
    for table in document.tables:
        if table not in schedule_tables and _looks_like_university_dates_table(table):
            _update_university_dates_table(table, new_course_data.university_dates)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    archive_before_write(output_path, eval_log_path=eval_log_path)
    document.save(str(output_path))


def _update_schedule(
    tables: list, new_dates_by_week_number: dict, new_break_weeks: list[Week]
) -> None:
    """Relabel every week row and rewrite the break rows, across all the
    schedule's tables (a schedule may be split into one table per module).
    Header and module-title rows are left alone (chalk.extractors.
    _docx_schedule.classify_row)."""
    week_rows: list[tuple] = []  # (new date or None, row)
    break_rows: list[tuple] = []  # (row, its table)
    for table in tables:
        for row in table.rows[1:]:  # row 0 is a header
            kind = classify_row(row)
            if kind == "week":
                week_rows.append((_relabel_week_row(row, new_dates_by_week_number), row))
            elif kind == "break":
                break_rows.append((row, table))
    _rewrite_break_rows(tables, break_rows, week_rows, new_break_weeks)


def _relabel_week_row(row, new_dates_by_week_number: dict):
    """Swap the date inside the row's "Week N (date)" label, in the label's
    own style ("8/24" or "Jan. 6") and keeping any text around it. Returns
    the week's new date (None if this week isn't in the new schedule)."""
    paragraph = next(p for p in row.cells[0].paragraphs if parse_week_label(p.text))
    label = parse_week_label(paragraph.text)
    new_date = new_dates_by_week_number.get(label.week_number)
    if new_date is None:
        return None
    old_label_text = paragraph.text[label.start : label.end]
    new_label_text = format_week_label(label.week_number, new_date, like=label)
    if not _replace_in_single_run(paragraph, old_label_text, new_label_text):
        text = paragraph.text
        _set_paragraph_text_preserving_format(
            paragraph, text[: label.start] + new_label_text + text[label.end :]
        )
    return new_date


def _rewrite_break_rows(
    tables: list, break_rows: list[tuple], week_rows: list[tuple], new_break_weeks: list[Week]
) -> None:
    """Make the schedule's break rows match `new_break_weeks` — same count,
    new labels, each placed just before the first week that starts after
    it. Existing break rows are reused in order (keeping their formatting
    and other cells, e.g. "No class"); extra breaks get a copy of the
    first one, and surplus rows are removed. A season-change rollover can
    change the number of breaks (chalk.rollover.season_change). A schedule
    with no break rows is left without them."""
    if not break_rows:
        return
    template_row, template_table = break_rows[0]
    template = deepcopy(template_row._tr)
    break_trs = [row._tr for row, _table in break_rows]
    for tr in break_trs:
        tr.getparent().remove(tr)

    for index, week in enumerate(sorted(new_break_weeks, key=lambda w: w.date_start)):
        tr = break_trs[index] if index < len(break_trs) else deepcopy(template)
        anchor = next(
            (
                row
                for new_date, row in week_rows
                if new_date is not None and new_date > week.date_start
            ),
            None,
        )
        if anchor is not None:
            anchor._tr.addprevious(tr)
        else:
            tables[-1]._tbl.append(tr)
        _set_first_paragraph_text_preserving_format(_Row(tr, template_table).cells[0], week.label)


def _update_front_matter_term(document, new_term: str) -> None:
    """Update the term wherever extraction read it from — a labeled line
    ("Term: Fall 2026", "Semester: Fall 2026"), a two-cell table row, or a
    header line like "Networking and Servers – Online Fall 2026" — so only
    the season and year change.

    Without this, re-extracting the written-out document would still see
    the old term label and derive the wrong calendar year from it
    (chalk.extractors._front_matter / docx_extractor's year_from_term),
    even though every week's date text was correctly updated. This is
    also the change PRD section 6.2's rollover preview shows first:
    "Term label: 'Fall 2026' -> 'Fall 2027'".
    """
    slots = list(front_matter_slots(document))
    index = term_line_index([slot[1] for slot in slots], [slot[2] for slot in slots])
    if index is None:  # pragma: no cover - extraction requires a term, so one is always found
        return
    paragraph = slots[index][0]
    if not _replace_term_in_single_run(paragraph, new_term):
        new_text = replace_term_text(paragraph.text, new_term)
        if new_text is None:
            new_text = f"Term: {new_term}" if parse_labeled_line(paragraph.text) else new_term
        _set_paragraph_text_preserving_format(paragraph, new_text)


def _replace_term_in_single_run(paragraph, new_term: str) -> bool:
    """Swap the term inside the one run that holds it, leaving every other
    run (and its formatting) alone. False if no single run holds it."""
    for run in paragraph.runs:
        replaced = replace_term_text(run.text, new_term)
        if replaced is not None:
            run.text = replaced
            return True
    return False


def _replace_in_single_run(paragraph, old: str, new: str) -> bool:
    """Replace `old` inside the one run that holds all of it, leaving other
    runs alone. False if it spans runs."""
    for run in paragraph.runs:
        if old in run.text:
            run.text = run.text.replace(old, new, 1)
            return True
    return False


def _looks_like_university_dates_table(table) -> bool:
    if not table.rows:  # pragma: no cover - python-docx tables always have >=1 row
        return False
    header = [cell.text.strip().lower() for cell in table.rows[0].cells]
    return "event" in header and "date" in header


def _update_university_dates_table(table, university_dates: list[UniversityDate]) -> None:
    """Pair rows with `university_dates` by position when the counts
    match: the extractor read one entry per row with a parseable date, in
    order, and rollover keeps that order and count. Position (not event
    name) is what lets a season-change rollover rename "Fall Break" to
    "Spring Break". Otherwise fall back to matching rows by event name."""
    dated_rows = [row for row in table.rows[1:] if _has_parseable_date(row.cells[1].text)]
    if len(dated_rows) == len(university_dates):
        pairs = zip(dated_rows, university_dates)
    else:
        dates_by_event = {entry.event: entry for entry in university_dates}
        pairs = [
            (row, dates_by_event[row.cells[0].text.strip()])
            for row in table.rows[1:]
            if row.cells[0].text.strip() in dates_by_event
        ]
    for row, entry in pairs:
        if row.cells[0].text.strip() != entry.event:
            _set_first_paragraph_text_preserving_format(row.cells[0], entry.event)
        _set_first_paragraph_text_preserving_format(row.cells[1], _format_university_date(entry))


def _has_parseable_date(text: str) -> bool:
    return bool(DATE_RANGE_RE.search(text) or FULL_DATE_RE.search(text))


def _format_university_date(entry: UniversityDate) -> str:
    if entry.date is not None:
        return f"{entry.date.month}/{entry.date.day}/{entry.date.year}"
    return (
        f"{entry.date_start.month}/{entry.date_start.day} - "
        f"{entry.date_end.month}/{entry.date_end.day}"
    )


def _set_first_paragraph_text_preserving_format(cell, new_text: str) -> None:
    _set_paragraph_text_preserving_format(cell.paragraphs[0], new_text)


def _set_paragraph_text_preserving_format(paragraph, new_text: str) -> None:
    """Mutate a paragraph's existing runs in place, rather than clearing
    it and adding a fresh (unformatted) run. `cell.text = "..."` or a
    clear-and-rebuild would silently drop bold/color/font formatting —
    see python-openxml/python-docx#290."""
    runs = paragraph.runs
    if not runs:  # pragma: no cover - a paragraph with visible text always has >=1 run
        paragraph.add_run(new_text)
        return
    runs[0].text = new_text
    for extra_run in runs[1:]:
        extra_run.text = ""
