"""Multi-page PDFs with positioned text and ruled tables, hand-assembled
(like pdf_builder) so the suite needs no PDF-writing dependency.
pdfplumber finds the tables from the ruling lines and measures the text
with Helvetica's standard metrics, so these exercise the real local PDF
reader end to end.

Coordinates are in points from the top-left of a US Letter page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
FONT_SIZE = 10
LINE_HEIGHT = 12
CELL_PADDING = 4


@dataclass
class PageBuilder:
    ops: list[str] = field(default_factory=list)

    def text(self, x: float, top: float, text: str, size: int = FONT_SIZE) -> PageBuilder:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        baseline = PAGE_HEIGHT - top - size
        self.ops.append(f"BT /F1 {size} Tf {x} {baseline} Td ({escaped}) Tj ET")
        return self

    def lines(self, x: float, top: float, lines: list[str]) -> PageBuilder:
        for index, line in enumerate(lines):
            self.text(x, top + index * LINE_HEIGHT, line)
        return self

    def table(self, x: float, top: float, column_widths: list[float], rows: list[list[list[str]]]) -> float:
        """Draw a ruled table; each cell is a list of lines. Returns the
        table's bottom."""
        heights = [max(1, *(len(cell) for cell in row)) * LINE_HEIGHT + 2 * CELL_PADDING for row in rows]
        right = x + sum(column_widths)
        bottom = top + sum(heights)
        row_top = top
        for row, height in zip(rows, heights):
            self._line(x, row_top, right, row_top)
            cell_x = x
            for width, cell in zip(column_widths, row):
                self.lines(cell_x + CELL_PADDING, row_top + CELL_PADDING, cell)
                cell_x += width
            row_top += height
        self._line(x, bottom, right, bottom)
        column_x = x
        for width in [0, *column_widths]:
            column_x += width
            self._line(column_x, top, column_x, bottom)
        return bottom

    def _line(self, x0: float, top0: float, x1: float, top1: float) -> None:
        self.ops.append(f"0.5 w {x0} {PAGE_HEIGHT - top0} m {x1} {PAGE_HEIGHT - top1} l S")


def build_pdf(path: Path, pages: list[PageBuilder]) -> Path:
    font_number = 3 + 2 * len(pages)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [%s] /Count %d >>"
        % (" ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages))).encode(), len(pages)),
    ]
    for index, page in enumerate(pages):
        stream = "\n".join(page.ops).encode("cp1252")  # the font's WinAnsiEncoding
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
            b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (PAGE_WIDTH, PAGE_HEIGHT, 4 + 2 * index, font_number)
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)
    path.write_bytes(bytes(out))
    return path


# ---- A two-page syllabus ---------------------------------------------------------

SCHEDULE_COLUMNS = [80, 200, 170]
SCHEDULE_HEADER = [["Week"], ["Topics"], ["Assignment Due"]]


def build_two_page_syllabus(path: Path) -> Path:
    """IS 6640, Fall 2026: a header, objectives, a grading table, and a
    schedule that breaks across the page — week 2's topic cell continues
    at the top of page 2 under a repeated header — then a break row and
    two more weeks. Both pages carry a "Page N" footer."""
    first = PageBuilder()
    first.lines(72, 60, ["Networking and Servers", "IS 6640 | Fall 2026", "3 Credit Hours"])
    first.text(72, 110, "Instructor: Dr. Ada Lovelace")
    first.text(72, 140, "LEARNING OBJECTIVES")
    first.text(72, 156, "By the end of this course, you will be able to:")
    first.lines(72, 170, ["• Explain how IP subnetting divides a network", "• Configure a VLAN on a managed switch"])
    first.text(72, 210, "GRADING")
    grading_bottom = first.table(
        72, 226, [150, 80], [[["Assessment"], ["Weight"]], [["Labs"], ["60%"]], [["Final exam"], ["40%"]]]
    )
    first.text(72, grading_bottom + 20, "COURSE SCHEDULE")
    first.table(
        72,
        grading_bottom + 36,
        SCHEDULE_COLUMNS,
        [
            SCHEDULE_HEADER,
            [["Week 1 (8/24)"], ["Course introduction"], ["Lab 0 due"]],
            [["Week 2 (8/31)"], ["Subnetting fundamentals and"], []],
        ],
    )
    first.text(72, 760, "IS 6640 | Page 1")

    second = PageBuilder()
    second.table(
        72,
        60,
        SCHEDULE_COLUMNS,
        [
            SCHEDULE_HEADER,
            [[], ["address planning"], ["Lab 1 due"]],
            [["Week 3 (9/7)"], ["VLANs"], ["–"]],
            [["Fall Break", "(10/10 - 10/18)"], [], []],
            [["Week 4 (10/19)"], ["Routing basics"], ["Quiz 1 due"]],
        ],
    )
    second.text(72, 760, "IS 6640 | Page 2")
    return build_pdf(path, [first, second])


def build_pdf_without_text(path: Path) -> Path:
    """Only ruling lines — what a scanned page looks like to a text reader."""
    page = PageBuilder()
    page.table(72, 72, [200, 200], [[[], []], [[], []]])
    return build_pdf(path, [page])
