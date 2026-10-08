"""Word (.docx) rollover writer (F-02, Word path).

Applies a rolled-over CourseData's new dates onto a fresh copy of the
original Word document — mutating each week-label cell's existing run
text in place rather than clearing and rebuilding the paragraph, so
formatting (bold, color, font) survives (python-openxml/python-docx#290;
see PLAN.md Risk #1). All other cell content (topics, assignments, notes)
is left untouched, per PRD section 6.2: "All other cell content
preserved." When the course length changes, rows of dropped weeks are
removed and added weeks get a copy of the last week row with placeholder
content. Quiz/exam/lab numbering embedded in untouched text is
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
from docx.text.paragraph import Paragraph

from chalk.archiving import archive_before_write
from chalk.extractors._dates import DATE_RANGE_RE, FULL_DATE_RE
from chalk.extractors._docx_schedule import (
    classify_row,
    distinct_cells,
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

    new_weeks_by_number = {
        week.week_number: week
        for week in new_course_data.weeks
        if not week.is_break and week.date is not None
    }
    new_break_weeks = [week for week in new_course_data.weeks if week.is_break]

    schedule_tables = [table for table in document.tables if looks_like_schedule_table(table)]
    _update_schedule(schedule_tables, new_weeks_by_number, new_break_weeks)
    for table in document.tables:
        if table not in schedule_tables and _looks_like_university_dates_table(table):
            _update_university_dates_table(table, new_course_data.university_dates)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    archive_before_write(output_path, eval_log_path=eval_log_path)
    document.save(str(output_path))


def _update_schedule(tables: list, new_weeks_by_number: dict, new_break_weeks: list[Week]) -> None:
    """Make the week rows match the new schedule, then rewrite the break
    rows, across all the schedule's tables (a schedule may be split into
    one table per module). Header and module-title rows are left alone
    (chalk.extractors._docx_schedule.classify_row)."""
    week_rows: list[tuple] = []  # (row, its table)
    break_rows: list[tuple] = []  # (row, its table)
    for table in tables:
        for row in table.rows[1:]:  # row 0 is a header
            kind = classify_row(row)
            if kind == "week":
                week_rows.append((row, table))
            elif kind == "break":
                break_rows.append((row, table))
    dated_rows = _update_week_rows(tables, week_rows, new_weeks_by_number)
    _rewrite_break_rows(tables, break_rows, dated_rows, new_break_weeks)


def _update_week_rows(tables: list, week_rows: list[tuple], new_weeks_by_number: dict) -> list[tuple]:
    """Relabel the rows of weeks that stay, remove the rows of weeks a
    shorter course drops, and add a row after the last week for each week
    a longer course adds. Returns (new date, row) for every week row left.

    An added row is a copy of the last week row, so it keeps the table's
    formatting; its cells get the new week's label and placeholder content
    instead of the copied text."""
    if not week_rows:  # pragma: no cover - extraction requires a week row
        return []
    template_row, template_table = week_rows[-1]
    template_tr = deepcopy(template_row._tr)
    template_label = _label_paragraph_and_label(template_row)[1]

    dated_rows: list[tuple] = []
    kept_numbers: set[int] = set()
    for row, _table in week_rows:
        week = new_weeks_by_number.get(_label_paragraph_and_label(row)[1].week_number)
        if week is None:
            row._tr.getparent().remove(row._tr)
            continue
        _relabel_week_row(row, week.date)
        dated_rows.append((week.date, row))
        kept_numbers.add(week.week_number)

    anchor_tr = dated_rows[-1][1]._tr if dated_rows else None
    for number in sorted(set(new_weeks_by_number) - kept_numbers):
        week = new_weeks_by_number[number]
        row = _Row(deepcopy(template_tr), template_table)
        _fill_new_week_row(row, week, template_label)
        if anchor_tr is not None:
            anchor_tr.addnext(row._tr)
        else:  # pragma: no cover - a course always keeps at least one week
            tables[-1]._tbl.append(row._tr)
        anchor_tr = row._tr
        dated_rows.append((week.date, row))
    return dated_rows


def _label_paragraph_and_label(row) -> tuple:
    paragraph = next(p for p in row.cells[0].paragraphs if parse_week_label(p.text))
    return paragraph, parse_week_label(paragraph.text)


def _relabel_week_row(row, new_date) -> None:
    """Swap the date inside the row's "Week N (date)" label, in the label's
    own style ("8/24" or "Jan. 6") and keeping any text around it."""
    paragraph, label = _label_paragraph_and_label(row)
    old_label_text = paragraph.text[label.start : label.end]
    new_label_text = format_week_label(label.week_number, new_date, like=label)
    if not _replace_in_single_run(paragraph, old_label_text, new_label_text):
        text = paragraph.text
        _set_paragraph_text_preserving_format(
            paragraph, text[: label.start] + new_label_text + text[label.end :]
        )


def _fill_new_week_row(row, week: Week, like) -> None:
    """Label cell: the new "Week N (date)". Second cell: the week's topics,
    assignments, and a "Note:" line (so re-extraction reads it back as the
    note). Any other cells are emptied. A one-column table gets it all in
    the label cell."""
    label = format_week_label(week.week_number, week.date, like=like)
    content = [*week.topics, *week.assignments, *([f"Note: {week.notes}"] if week.notes else [])]
    cells = distinct_cells(row)
    if len(cells) == 1:
        _fill_cell(cells[0], [label, *content])
        return
    _fill_cell(cells[0], [label])
    _fill_cell(cells[1], content)
    for cell in cells[2:]:
        _fill_cell(cell, [])


def _fill_cell(cell, lines: list[str]) -> None:
    """Replace a copied cell's text with one paragraph per line, each a
    copy of the cell's first paragraph so the formatting carries over."""
    first, *rest = cell.paragraphs
    for paragraph in rest:
        paragraph._p.getparent().remove(paragraph._p)
    _set_paragraph_text_preserving_format(first, lines[0] if lines else "")
    previous = first._p
    for line in lines[1:]:
        new_p = deepcopy(first._p)
        previous.addnext(new_p)
        _set_paragraph_text_preserving_format(Paragraph(new_p, cell), line)
        previous = new_p


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
    if not runs:  # an empty cell in a copied row
        paragraph.add_run(new_text)
        return
    runs[0].text = new_text
    for extra_run in runs[1:]:
        extra_run.text = ""
