"""Turning the tables pdfplumber finds into the syllabus's real tables.

pdfplumber reports every ruled box as a table, so most "tables" in a
syllabus PDF are just boxed paragraphs; only the schedule, grading, and
similar grid tables are kept as tables (the rest is read as text). A
schedule usually breaks across pages, so its pieces are stitched back
together: a repeated header row is dropped, and a row cut off at a page
break (no week label in its first cell) is merged into the week row above
it. A schedule split by module titles stays one table per module, which
the Word schedule reader already handles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from chalk.extractors._docx_schedule import parse_week_label
from chalk.pdf_import.blocks import Block, Paragraph, Table
from chalk.pdf_import.reflow import ends_in_url, is_bullet, join_wrapped

Row = list[list[str]]  # cells -> the cell's paragraphs

# A cell holding only a dash means "nothing this week".
_PLACEHOLDER_RE = re.compile(r"^[-–—]+$")
_SENTENCE_END = (".", "?", "!", ")", "”", "\"")


@dataclass(frozen=True)
class RawTable:
    """A table as found on one page. `is_real` is False for a ruled box at
    the top of a page that is passed along only because it may be the
    rest of a schedule row cut off at the page break."""

    rows: tuple[tuple[tuple[str, ...], ...], ...]
    is_real: bool = True

    @property
    def is_schedule(self) -> bool:
        return any(_is_week_row(row) for row in self.rows)


def normalize_rows(rows: list[Row]) -> list[Row]:
    """Drop placeholder dashes, then rows and columns that are empty all
    the way through (a stray empty column often appears on one page of a
    split table)."""
    rows = [[[text for text in cell if not _PLACEHOLDER_RE.match(text)] for cell in row] for row in rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        return []
    width = max(len(row) for row in rows)
    rows = [row + [[] for _ in range(width - len(row))] for row in rows]
    keep = [i for i in range(width) if any(row[i] for row in rows)]
    return [[row[i] for i in keep] for row in rows]


def is_real_table(rows: list[Row]) -> bool:
    """A schedule (a row starting with "Week N (date)"), or a grid where
    most rows fill two or more cells. A boxed paragraph or a bulleted list
    that pdfplumber split into columns is neither."""
    if not rows or max(len(row) for row in rows) < 2:
        return False
    if any(_is_week_row(row) for row in rows):
        return True
    filled = sum(1 for row in rows if sum(1 for cell in row if cell) >= 2)
    return len(rows) >= 2 and filled * 2 > len(rows)


def freeze(rows: list[Row], *, is_real: bool = True) -> RawTable:
    return RawTable(tuple(tuple(tuple(cell) for cell in row) for row in rows), is_real)


def assemble(items: list[Paragraph | RawTable]) -> list[Block]:
    """The document's blocks in order, with schedule pieces stitched
    together."""
    blocks: list[Paragraph | list[Row]] = []
    schedule: list[Row] | None = None  # the schedule piece directly above, if any
    header: Row | None = None

    for item in items:
        if isinstance(item, Paragraph):
            blocks.append(item)
            schedule = None
            continue
        rows = [[list(cell) for cell in row] for row in item.rows]
        if item.is_schedule:
            schedule = _add_schedule_piece(blocks, schedule, rows, header)
            header = header or _header_of(schedule)
        elif schedule is not None and not item.is_real and _same_width(rows, schedule):
            _merge_into_last_week(schedule, rows)  # a page holding only the end of a row
        elif item.is_real:
            blocks.append(rows)
            schedule = None
        else:
            blocks += [Paragraph(text) for row in rows for cell in row for text in cell]
            schedule = None

    return [block if isinstance(block, Paragraph) else _to_table(block) for block in blocks]


def _add_schedule_piece(blocks: list, schedule: list[Row] | None, rows: list[Row], header: Row | None) -> list[Row]:
    """Add one schedule piece. Directly after another piece it continues
    that table; after other text it starts a new table (one per module),
    given the schedule's header row if it lacks one. Returns the table
    the piece went into."""
    lead, body = _split_lead(rows)
    repeated_header = [row for row in lead if _same_row(row, header)]
    cut_off = [row for row in lead if not _same_row(row, header)]
    if schedule is not None:
        _merge_into_last_week(schedule, cut_off)
        schedule.extend(body)
        return schedule
    if header is not None and cut_off:
        # A row cut off at a page break with something (e.g. a module
        # title) in between: it still belongs to the last week before it.
        previous = next((b for b in reversed(blocks) if isinstance(b, list) and _has_week(b)), None)
        if previous is not None:
            _merge_into_last_week(previous, cut_off)
            lead = repeated_header
    new_table = (lead or [header or _synthetic_header(body)]) + body
    blocks.append(new_table)
    return new_table


def _is_week_row(row) -> bool:
    return bool(row) and parse_week_label(" ".join(row[0])) is not None


def _has_week(rows: list[Row]) -> bool:
    return any(_is_week_row(row) for row in rows)


def _split_lead(rows: list[Row]) -> tuple[list[Row], list[Row]]:
    """(rows before the first week row, the rest)."""
    first_week = next(i for i, row in enumerate(rows) if _is_week_row(row))
    return rows[:first_week], rows[first_week:]


def _header_of(schedule: list[Row]) -> Row | None:
    lead, _ = _split_lead(schedule)
    return lead[-1] if lead else None


def _synthetic_header(body: list[Row]) -> Row:
    width = max(len(row) for row in body)
    return [["Week"]] + [[] for _ in range(width - 1)]


def _same_row(row: Row, other: Row | None) -> bool:
    return other is not None and _row_key(row) == _row_key(other)


def _row_key(row: Row) -> list[str]:
    return [" ".join(" ".join(cell).lower().split()) for cell in row]


def _same_width(rows: list[Row], other: list[Row]) -> bool:
    return max(len(row) for row in rows) == max(len(row) for row in other)


def _merge_into_last_week(table: list[Row], rows: list[Row]) -> None:
    """Append each row's cell paragraphs to the matching cells of the
    table's last week row (column by column; extra columns go into the
    last cell)."""
    target = next(row for row in reversed(table) if _is_week_row(row))
    for row in rows:
        for index, cell in enumerate(row):
            _append_paragraphs(target[min(index, len(target) - 1)], cell)


def _append_paragraphs(cell: list[str], more: list[str]) -> None:
    """Most page breaks fall mid-paragraph ("Reporting and Issue" /
    "Management"), so the first cut-off paragraph is rejoined unless the
    one before it ended a sentence or it's a bullet. The line positions
    from the previous page are gone by now, so this can't be exact; the
    Review tab is where a wrong join gets fixed."""
    if cell and more and not is_bullet(more[0]) and (
        ends_in_url(cell[-1]) or not cell[-1].rstrip().endswith(_SENTENCE_END)
    ):
        cell[-1] = join_wrapped(cell[-1], more[0])
        more = more[1:]
    cell.extend(more)


def _to_table(rows: list[Row]) -> Table:
    width = max(len(row) for row in rows)
    rows = [row + [[] for _ in range(width - len(row))] for row in rows]
    return Table(
        tuple(
            tuple(_single_line(cell) if index == 0 else tuple(cell) for index, cell in enumerate(row))
            for row in rows
        )
    )


def _single_line(paragraphs: list[str]) -> tuple[str, ...]:
    """A row's first cell is a label ("Week 1" / "(Jan. 6)"): one line, so
    the Word schedule reader finds the whole label in its first paragraph."""
    return (" ".join(paragraphs),) if paragraphs else ()
