"""Find the text a rollover changed in the original PDF's text.

pdfplumber reads a page as lines, but a line of a table runs across every
column: "Week 1   Course Introduction   Review Syllabus". So each line is
split into column segments wherever the gap between two characters is
wider than a space. A table cell's text may also wrap ("Week 1" with
"(Jan. 6)" on the line below it), so a change can continue into the
segment directly below, in the same column.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import pdfplumber

from chalk.errors import ChalkError

# A gap wider than this (in ems) between two characters on a line starts
# a new column segment; a space between words is about a quarter em.
_COLUMN_GAP_EMS = 0.6
# The segment below a segment starts within this many points of its left
# edge and within this many line heights of its top.
_SAME_COLUMN_POINTS = 3.0
_NEXT_LINE_HEIGHTS = 2.0
# Lines this close to the top or bottom edge (fraction of page height) are
# running headers and footers.
_MARGIN_RATIO = 0.07


class PdfRolloverError(ChalkError):
    """The PDF copy can't be written exactly; the Word file still is."""


@dataclass(frozen=True)
class Line:
    page: int
    top: float
    chars: tuple  # non-space pdfplumber characters, left to right

    @property
    def compact(self) -> str:
        return "".join(char["text"] for char in self.chars)


@dataclass(frozen=True)
class Segment:
    page: int
    top: float
    x0: float
    size: float
    chars: tuple
    in_margin: bool


@dataclass(frozen=True)
class Target:
    """Characters in the PDF to replace with `new`, all on one page."""

    page: int
    chars: tuple
    new: str


@dataclass(frozen=True)
class PdfText:
    lines: list[Line]
    segments: list[Segment]  # in reading order
    chars: list[list[dict]]  # every character, per page


def read_pdf_text(pdf_path) -> PdfText:
    lines: list[Line] = []
    segments: list[Segment] = []
    chars_by_page: list[list[dict]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages):
            if page.rotation:
                raise PdfRolloverError("The PDF has rotated pages, so Chalk can't edit it exactly.")
            chars_by_page.append(page.chars)
            for text_line in page.extract_text_lines(return_chars=True):
                chars = tuple(
                    sorted(
                        (c for c in text_line["chars"] if c["text"].strip()), key=lambda c: c["x0"]
                    )
                )
                if not chars:
                    continue
                lines.append(Line(page_index, text_line["top"], chars))
                in_margin = text_line["top"] < page.height * _MARGIN_RATIO or text_line[
                    "bottom"
                ] > page.height * (1 - _MARGIN_RATIO)
                segments += [
                    Segment(
                        page_index,
                        text_line["top"],
                        piece[0]["x0"],
                        piece[0]["size"],
                        piece,
                        in_margin,
                    )
                    for piece in _split_columns(chars)
                ]
    return PdfText(lines, segments, chars_by_page)


def _split_columns(chars: tuple) -> list[tuple]:
    pieces = [[chars[0]]]
    for previous, char in pairwise(chars):
        if char["x0"] - previous["x1"] > _COLUMN_GAP_EMS * max(previous["size"], 1.0):
            pieces.append([])
        pieces[-1].append(char)
    return [tuple(piece) for piece in pieces]


def locate(changes: list, text: PdfText) -> list[Target]:
    """Find each change (chalk.rollover.pdf_rollover.TextChange) in the
    PDF, with the words before it, in reading order: each search starts
    at the previous find and only then wraps around. Raises
    PdfRolloverError if one can't be found."""
    targets: list[Target] = []
    used: set[int] = set()  # id() of characters already changed
    cursor = 0
    for change in changes:
        found = _find(change, text.segments, cursor, used)
        if found is None:
            shown = " ".join([*change.before, change.old])
            raise PdfRolloverError(f'Chalk couldn\'t find "{shown}" in the PDF to change it.')
        cursor, chars = found
        targets.append(Target(text.segments[cursor].page, chars, change.new))
        used.update(id(char) for char in chars)
    return targets


def _find(change, segments: list[Segment], cursor: int, used: set[int]) -> tuple[int, tuple] | None:
    """The first unused occurrence of the change, trying all its words of
    context first and then only the last one (a wrapped cell can leave
    the first word on a line of its own, out of reach)."""
    old = _compact(change.old)
    contexts = [
        _compact("".join(change.before[-n:])) for n in range(len(change.before), 0, -1)
    ] or [""]
    for context in contexts:
        for index in [*range(cursor, len(segments)), *range(cursor)]:
            for unit in _units(segments, index):
                compact = "".join(char["text"] for char in unit)
                position = compact.find(context + old)
                while position != -1:
                    chars = unit[position + len(context) : position + len(context) + len(old)]
                    if not any(id(char) in used for char in chars):
                        return index, chars
                    position = compact.find(context + old, position + 1)
    return None


def _units(segments: list[Segment], index: int) -> list[tuple]:
    """The segment's characters, and those followed by the segment just
    below it in the same column."""
    segment = segments[index]
    below = _segment_below(segments, index)
    return [segment.chars] + ([segment.chars + below.chars] if below is not None else [])


def _segment_below(segments: list[Segment], index: int) -> Segment | None:
    segment = segments[index]
    candidates = [
        other
        for other in segments[index + 1 :]
        if other.page == segment.page
        and 0 < other.top - segment.top <= _NEXT_LINE_HEIGHTS * segment.size
        and abs(other.x0 - segment.x0) <= _SAME_COLUMN_POINTS
    ]
    return min(candidates, key=lambda other: other.top, default=None)


def margin_term_targets(
    text: PdfText, targets: list[Target], old_term: str, new_term: str
) -> list[Target]:
    """The old term in a running header or footer ("IS 4440 | Spring 2026"
    on every page), which the Word file read from the PDF leaves out."""
    taken = {id(char) for target in targets for char in target.chars}
    needle = _compact(old_term)
    found = []
    for segment in text.segments:
        compact = "".join(char["text"] for char in segment.chars)
        position = compact.find(needle) if segment.in_margin and needle else -1
        while position != -1:
            chars = segment.chars[position : position + len(needle)]
            if not any(id(char) in taken for char in chars):
                found.append(Target(segment.page, chars, new_term))
            position = compact.find(needle, position + len(needle))
    return found


def expected_lines(text: PdfText, targets: list[Target]) -> dict[tuple[int, float], str]:
    """How each changed line should read once the targets are replaced:
    (page, top) -> its text without spaces. A target's new text takes the
    place of its first character; the rest of its characters go."""
    first = {id(target.chars[0]): _compact(target.new) for target in targets}
    removed = {id(char) for target in targets for char in target.chars}
    expected = {}
    for line in text.lines:
        if not any(id(char) in removed for char in line.chars):
            continue
        expected[(line.page, line.top)] = "".join(
            first.get(id(char), "") if id(char) in removed else char["text"] for char in line.chars
        )
    return expected


def _compact(text: str) -> str:
    return "".join(text.split())
