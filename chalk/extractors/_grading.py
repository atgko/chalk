"""Grading tables, shared by the Word and markdown extractors.

A table can give weights as percentages ("Labs | 25%") or as points
("Labs | 250 pts", or "Labs | 250" under a "Points" header). Points are
turned into fractions of the course total: the table's own "Total" row
when it has one, else the sum of the rows. Using the Total row means a
row the extractor missed still shows up as weights short of 100%, which
Review and the CLI warn about.
"""

from __future__ import annotations

import re

from chalk.models import Assessment

PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
POINTS_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:pts?|points?)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^\s*(\d[\d,]*(?:\.\d+)?)\s*$")
_PERCENT_HEADER_RE = re.compile(r"weight|percent|%", re.IGNORECASE)
_POINTS_HEADER_RE = re.compile(r"\b(?:points?|pts?)\b", re.IGNORECASE)
_DIGIT_RE = re.compile(r"\d")

# Points weights are rounded to a hundredth of a percent, so 100 of 350
# points reads as 28.57% rather than 28.5714285...%.
_POINTS_WEIGHT_DECIMALS = 4

Row = list[str]


def header_column(header: Row) -> tuple[int, bool] | None:
    """The column holding weights, and whether it's in points, from a header
    row. A percentage column wins over a points column when a table has both.
    Cells with digits are data, not headers, so they never match."""
    labels = [(index, cell) for index, cell in enumerate(header) if index > 0 and not _DIGIT_RE.search(cell)]
    for index, cell in labels:
        if _PERCENT_HEADER_RE.search(cell):
            return index, False
    for index, cell in labels:
        if _POINTS_HEADER_RE.search(cell):
            return index, True
    return None


def headerless_points(rows: list[Row]) -> bool | None:
    """For a table with no header row: True if most rows' second cells say
    "pts"/"points", False if most are percentages, None if neither."""
    for pattern, points in ((PERCENT_RE, False), (POINTS_RE, True)):
        matching = [row for row in rows if pattern.search(row[1])]
        if len(matching) * 2 > len(rows) and pattern.search(rows[0][1]):
            return points
    return None


def parse_rows(rows: list[Row], column: int, *, points: bool) -> list[Assessment]:
    """Assessments from a grading table's data rows. Rows without a readable
    value are skipped, as is a "Total" row (whose points, if any, become the
    total that points are divided by)."""
    values: list[tuple[str, float]] = []
    stated_total = None
    for row in rows:
        name = row[0].strip()
        value = _read_value(row[column] if column < len(row) else "", points=points)
        if name.lower().startswith("total"):
            stated_total = value
        elif value is not None:
            values.append((name, value))
    if not points:
        return [Assessment(name=name, weight=value / 100) for name, value in values]

    total = stated_total or sum(value for _, value in values)
    if not total:
        return []
    return [
        Assessment(name=name, weight=min(round(value / total, _POINTS_WEIGHT_DECIMALS), 1)) for name, value in values
    ]


def _read_value(text: str, *, points: bool) -> float | None:
    if not points:
        match = PERCENT_RE.search(text)
    else:
        match = POINTS_RE.search(text) or _NUMBER_RE.match(text)
    return float(match.group(1).replace(",", "")) if match else None
