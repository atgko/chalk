"""The local PDF reader: pdfplumber -> paragraphs and tables, in reading
order. Runs entirely on this computer and costs nothing.

Per page: find the real tables (chalk.pdf_import.tables), read the text
outside them as lines with positions, drop running headers and footers
("Course # | Page 8"), and rejoin wrapped lines into paragraphs. Then the
pages are stitched together so a schedule split across pages becomes one
table again.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException

from chalk.errors import ExtractionError, ProtectedFileError
from chalk.pdf_import.blocks import Block, Paragraph
from chalk.pdf_import.reflow import Line, is_bullet, is_caps_heading, reflow_lines, strip_bullet
from chalk.pdf_import.tables import RawTable, assemble, freeze, is_real_table, normalize_rows

# Lines this close to the top or bottom edge (fraction of page height) are
# running headers/footers when they repeat or carry a page number.
_MARGIN_RATIO = 0.07
_PAGE_NUMBER_RE = re.compile(r"\bpage\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE)
_DIGITS_RE = re.compile(r"\d+")
# Fewer characters than this in the whole document means there's no text
# layer to read — almost always a scanned PDF.
_MIN_TEXT_CHARS = 200


def read_pdf_blocks(pdf_path) -> list[Block]:
    """Read a PDF syllabus into paragraphs and tables. Raises
    ProtectedFileError if it can't be opened and ExtractionError if it has
    no text layer (a scan)."""
    pages = _open_pages(Path(pdf_path))
    repeated = _repeated_margin_lines(pages)

    items: list[Paragraph | RawTable] = []
    for page in pages:
        body = [line for line in page.lines if not _is_running_line(line, page.height, repeated)]
        positioned = [(top, table) for top, table in page.tables]
        positioned += [(top, paragraph) for top, paragraph in _paragraphs(body)]
        items += [item for _, item in sorted(positioned, key=lambda pair: pair[0])]

    blocks = assemble(items)
    if _text_length(blocks) < _MIN_TEXT_CHARS:
        raise ExtractionError(
            "This PDF has no text Chalk can read — it's probably a scanned image. "
            "Open the original document and save it as Word (.docx) or as a PDF with text, "
            "then upload it again."
        )
    return blocks


def _open_pages(path: Path) -> list[_PageSnapshot]:
    try:
        with pdfplumber.open(path) as pdf:
            return [_PageSnapshot.of(page) for page in pdf.pages]
    except PdfminerException as exc:
        raise ProtectedFileError(
            "Chalk couldn't open this PDF. If it's password-protected, save a copy without "
            "the password and upload that; otherwise save it as Word (.docx) and upload that."
        ) from exc


@dataclass(frozen=True)
class _PageSnapshot:
    """What Chalk needs from a pdfplumber page, captured while the file is
    open: real tables, the tables that might continue a schedule, and the
    text lines outside the tables."""

    tables: list[tuple[float, RawTable]]  # (top, table)
    lines: list[Line]
    height: float

    @classmethod
    def of(cls, page) -> _PageSnapshot:
        found = []
        for table in page.find_tables():
            region = page.within_bbox(table.bbox)
            owners = _cell_owners(region, table)
            rows = normalize_rows(
                [[_cell_paragraphs(region, bbox, owners) for bbox in row.cells] for row in table.rows]
            )
            if rows:
                found.append((table.bbox, rows))
        text_tops = [line.top for line in _lines(page)]
        kept = [
            (bbox, freeze(rows, is_real=is_real_table(rows)))
            for bbox, rows in found
            if is_real_table(rows) or _may_continue_schedule(bbox, rows, text_tops, page.height)
        ]
        boxes = [bbox for bbox, _ in kept]
        outside = page.filter(lambda obj: not _inside_any(obj, boxes))
        return cls([(bbox[1], table) for bbox, table in kept], _lines(outside), page.height)


def _lines(page) -> list[Line]:
    return [
        Line(
            line["text"],
            line["x0"],
            line["x1"],
            line["top"],
            line["bottom"],
            _first_word_width(line["text"], line["chars"]),
        )
        for line in page.extract_text_lines(return_chars=True)
        if line["text"].strip()
    ]


def _first_word_width(text: str, chars: list[dict]) -> float | None:
    """Width of the line's first word. pdfplumber infers the spaces in a
    line's text from gaps, so `chars` may hold none: count the word's
    letters from the text and measure that many non-space characters."""
    letters = len(text.split()[0]) if text.split() else 0
    word = [char for char in chars if not char["text"].isspace()][:letters]
    return word[-1]["x1"] - word[0]["x0"] if word else None


def _cell_owners(region, table) -> dict[int, tuple]:
    """Which cell each character in the table belongs to (by object id):
    the cell its center falls in or — when the ruling lines pdfplumber
    found are narrower than the text, as in small tables — the nearest
    cell on its line."""
    cells = [bbox for row in table.rows for bbox in row.cells if bbox is not None]
    owners = {}
    for char in region.chars:
        cell = _owning_cell(char, cells)
        if cell is not None:
            owners[id(char)] = cell
    return owners


def _cell_paragraphs(region, bbox, owners: dict[int, tuple]) -> list[str]:
    """A table cell's text as paragraphs, rejoining lines that wrapped at
    the cell's right edge (its padding assumed equal on both sides)."""
    if bbox is None:  # part of a merged cell; the merged cell has the text
        return []
    lines = _lines(region.filter(lambda obj: owners.get(id(obj)) == bbox))
    if not lines:
        return []
    padding = max(0.0, min(line.x0 for line in lines) - bbox[0])
    return [text for _, text in reflow_lines(lines, right_edge=bbox[2] - padding)]


def _owning_cell(char, cells: list):
    center_x = (char["x0"] + char["x1"]) / 2
    center_y = (char["top"] + char["bottom"]) / 2
    same_line = [cell for cell in cells if cell[1] <= center_y <= cell[3]]
    if not same_line:
        return None
    return min(same_line, key=lambda cell: _horizontal_distance(center_x, cell))


def _horizontal_distance(x: float, cell) -> float:
    if cell[0] <= x <= cell[2]:
        return 0.0
    return min(abs(x - cell[0]), abs(x - cell[2]))


def _may_continue_schedule(bbox, rows, text_tops: list[float], height: float) -> bool:
    """A multi-column box at the very top of a page (no body text above it
    except a running header) may be the end of a schedule row from the
    page before; tables.assemble decides."""
    if max(len(row) for row in rows) < 2:
        return False
    above = [top for top in text_tops if top < bbox[1] - 1 and top > height * _MARGIN_RATIO]
    return not above


def _inside_any(obj, boxes) -> bool:
    if "x0" not in obj or "top" not in obj:
        return False
    center_x = (obj["x0"] + obj["x1"]) / 2
    center_y = (obj["top"] + obj["bottom"]) / 2
    return any(x0 <= center_x <= x1 and top <= center_y <= bottom for x0, top, x1, bottom in boxes)


# ---- Running headers and footers --------------------------------------------------


def _in_margin(line: Line, height: float) -> bool:
    return line.top < height * _MARGIN_RATIO or line.bottom > height * (1 - _MARGIN_RATIO)


def _margin_key(text: str) -> str:
    return _DIGITS_RE.sub("#", " ".join(text.lower().split()))


def _repeated_margin_lines(pages: list[_PageSnapshot]) -> set[str]:
    counts = Counter(
        key
        for page in pages
        for key in {_margin_key(line.text) for line in page.lines if _in_margin(line, page.height)}
    )
    return {key for key, count in counts.items() if count >= 2}


def _is_running_line(line: Line, height: float, repeated: set[str]) -> bool:
    if not _in_margin(line, height):
        return False
    return bool(_PAGE_NUMBER_RE.search(line.text)) or _margin_key(line.text) in repeated


# ---- Paragraphs -------------------------------------------------------------------


def _paragraphs(lines: list[Line]) -> list[tuple[float, Paragraph]]:
    """(top, paragraph) for the page's body lines."""
    return [(top, _classify(text)) for top, text in reflow_lines(lines)]


def _classify(text: str) -> Paragraph:
    if is_bullet(text):
        return Paragraph(strip_bullet(text), "bullet")
    if is_caps_heading(text):
        return Paragraph(text, "heading")
    return Paragraph(text)


def _text_length(blocks: list[Block]) -> int:
    total = 0
    for block in blocks:
        if isinstance(block, Paragraph):
            total += len(block.text)
        else:
            total += sum(len(text) for row in block.rows for cell in row for text in cell)
    return total
