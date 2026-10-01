"""Rejoining a PDF's visual lines into paragraphs.

A PDF stores text as positioned lines, so a sentence that wrapped is two
lines. These helpers decide, line by line, whether the next line carries
on the current paragraph or starts a new one. The rule a typesetter would
use: a line that ended with room to spare for the next line's first word
ended on purpose. Bullets, headings, vertical gaps, and sentence-ending
punctuation also start a new paragraph; a line starting in lowercase
always continues one. A trailing colon doesn't end a paragraph ("Case
Write-up #3: AI in Radiology:" often wraps there); the bullets that
usually follow a lead-in colon start their own paragraphs anyway.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

# Symbol bullets may touch their text ("●Item"); dash-like bullets need a
# space after them, or "-scope-creep" (a wrapped URL) would read as one.
_BULLET_RE = re.compile(r"^(?:[●•▪◦‣○■□➢➤✓]\s*|[-–*]\s+)")
_TERMINAL_CHARS = ".?!)”\""
_CAPS_HEADING_MAX_CHARS = 60
# A gap between lines taller than this fraction of a line's height is a
# paragraph break even when the line above was full.
_PARAGRAPH_GAP_RATIO = 0.6
# How far short of the right edge (in average letter widths) a line can
# end and still count as full.
_EDGE_SLACK_CHARS = 0.5


@dataclass(frozen=True)
class Line:
    """One visual line of text and its position on the page (points).
    `first_word_width` is the measured width of the line's first word,
    when known; otherwise it's estimated from the line's average letter."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    first_word_width: float | None = None


def is_bullet(text: str) -> bool:
    stripped = text.strip()
    match = _BULLET_RE.match(stripped)
    return bool(match) and len(stripped) > match.end()


def strip_bullet(text: str) -> str:
    return _BULLET_RE.sub("", text.strip(), count=1).strip()


def is_caps_heading(text: str) -> bool:
    """"COURSE DESCRIPTION": short, all capitals, with letters in it."""
    stripped = text.strip()
    return (
        stripped.isupper()
        and len(stripped) <= _CAPS_HEADING_MAX_CHARS
        and any(c.isalpha() for c in stripped)
    )


def join_wrapped(previous: str, following: str) -> str:
    """Join a wrapped line onto the text before it. A URL, or a word
    broken with a hyphen at the line end, continues without a space."""
    if ends_in_url(previous) or (previous.endswith("-") and not previous.endswith(" -")):
        return previous + following
    return f"{previous} {following}"


def ends_in_url(text: str) -> bool:
    token = text.rsplit(" ", 1)[-1]
    return "://" in token or token.startswith("www.")


def reflow_lines(lines: list[Line], right_edge: float | None = None) -> list[tuple[float, str]]:
    """(top of its first line, text) for each paragraph in `lines`, in
    order. `right_edge` is where a full line ends — the text column's (or
    table cell's) right side; by default the widest line's end."""
    if not lines:
        return []
    edge = right_edge if right_edge is not None else max(line.x1 for line in lines)
    paragraphs = [(lines[0].top, lines[0].text.strip())]
    for previous, line in pairwise(lines):
        top, text = paragraphs[-1]
        if _continues(text, previous, line, edge):
            paragraphs[-1] = (top, join_wrapped(text, line.text.strip()))
        else:
            paragraphs.append((line.top, line.text.strip()))
    return paragraphs


def _continues(paragraph: str, previous: Line, line: Line, right_edge: float) -> bool:
    """Whether `line` carries on `paragraph`, whose last visual line is
    `previous`."""
    # A caps line *after* a full line is a wrapped word ("...Front-Liners
    # at" / "NUH"), not a heading, so only the line above is checked here;
    # a real heading follows a short line, which the room test catches.
    text = line.text.strip()
    if is_bullet(text) or is_caps_heading(previous.text):
        return False
    line_height = previous.bottom - previous.top
    if line.top - previous.bottom > _PARAGRAPH_GAP_RATIO * line_height:
        return False
    if ends_in_url(paragraph) or text[:1].islower():
        return True
    if previous.text.rstrip().endswith(tuple(_TERMINAL_CHARS)):
        return False
    char_width = (previous.x1 - previous.x0) / max(1, len(previous.text))
    word_width = line.first_word_width
    if word_width is None:
        word_width = len(text.split(" ", 1)[0]) * char_width
    # A space, plus slack for a cell's right padding being a little wider
    # than its left (the edge is estimated from the left padding).
    return right_edge - previous.x1 < word_width + char_width * (1 + _EDGE_SLACK_CHARS)
