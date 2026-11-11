"""The demo's PDF syllabus: the same sample IS 6640 course as the Word
one, laid out as a PDF, so teammates can try the PDF path (Upload's free
reader, or Read it with AI) without a syllabus of their own.

Written with reportlab (already used for assignment PDFs). The schedule
and grading tables have ruling lines, which is what Chalk's free PDF
reader (pdfplumber) needs to see them as tables. Headings are in capitals
and bullets are dashes, as in many real syllabi, since that's what the
reader goes by (the standard PDF fonts have no "•").
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from chalk.demo_content import (
    _IS6640_ASSESSMENTS,
    _IS6640_OBJECTIVES,
    _IS6640_WEEKS,
    SAMPLE_NOTICE,
)

_FIRST_WEEK = dt.date(2026, 8, 24)
_BREAK_AFTER_WEEK = 7
_GRID = TableStyle(
    [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]
)


def build_is6640_pdf_syllabus(path: Path) -> Path:
    """The Fall 2026 IS 6640 sample syllabus as a PDF, with the same
    front matter, objectives, 10-week schedule, Fall Break, and grading as
    `build_is6640_word_syllabus`."""
    styles = getSampleStyleSheet()
    body, heading = styles["BodyText"], styles["Heading1"]
    story = [Paragraph(f"<i>{SAMPLE_NOTICE}</i>", body)]
    for label, value in (
        ("Course", "IS 6640 Networking and Servers"),
        ("Course Number", "IS 6640"),
        ("Section", "090"),
        ("Credits", "3"),
        ("Term", "Fall 2026"),
        ("Instructor", "Sample Instructor"),
        ("Meeting Pattern", "Online async"),
    ):
        story.append(Paragraph(f"{label}: {value}", body))

    story.append(Paragraph("LEARNING OBJECTIVES", heading))
    story += [Paragraph(f"- {objective}", body) for objective in _IS6640_OBJECTIVES]

    story.append(Paragraph("SCHEDULE", heading))
    story.append(_table([["Week", "Topics / Assignments"], *_schedule_rows()], [2.1 * inch, 4.4 * inch]))

    story.append(Paragraph("GRADING", heading))
    grading = [["Assessment", "Weight"], *([name, f"{weight}%"] for name, weight in _IS6640_ASSESSMENTS)]
    story.append(_table(grading, [3 * inch, 1.5 * inch]))
    story.append(Spacer(1, 0.2 * inch))

    SimpleDocTemplate(str(path), pagesize=LETTER, title="IS 6640 Sample Syllabus").build(story)
    return path


def _schedule_rows() -> list[list[str]]:
    rows = []
    for number, (topics, assignments, note) in enumerate(_IS6640_WEEKS, start=1):
        week_date = _FIRST_WEEK + dt.timedelta(days=7 * (number - 1))
        lines = [*topics, *assignments, *([f"Note: {note}"] if note else [])]
        rows.append([f"Week {number} ({week_date.month}/{week_date.day})", "\n".join(lines)])
        if number == _BREAK_AFTER_WEEK:
            rows.append(["Fall Break (10/10 - 10/18)", ""])
    return rows


def _table(rows: list[list[str]], widths: list[float]) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(_GRID)
    return table
