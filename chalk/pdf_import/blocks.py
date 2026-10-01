"""The neutral document model a PDF is read into before it's written out
as Word: an ordered list of paragraphs and tables. Both PDF readers (the
local layout reader and the AI reader) produce it, and one writer turns
it into a .docx, so the rest of Chalk only ever sees a Word syllabus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ParagraphKind = Literal["body", "heading", "bullet"]


@dataclass(frozen=True)
class Paragraph:
    text: str
    kind: ParagraphKind = "body"


@dataclass(frozen=True)
class Table:
    """rows -> cells -> the cell's paragraphs (one string each)."""

    rows: tuple[tuple[tuple[str, ...], ...], ...]


Block = Paragraph | Table


def blocks_as_text(blocks: list[Block]) -> str:
    """A plain-text rendering (tables as "a | b" rows, a cell's paragraphs
    joined by " / ") — the AI reader's input, and handy in tests."""
    lines: list[str] = []
    for block in blocks:
        if isinstance(block, Paragraph):
            prefix = {"heading": "## ", "bullet": "- "}.get(block.kind, "")
            lines.append(prefix + block.text)
            continue
        lines.append("")
        lines += ["| " + " | ".join(" / ".join(cell) for cell in row) + " |" for row in block.rows]
        lines.append("")
    return "\n".join(lines).strip()
