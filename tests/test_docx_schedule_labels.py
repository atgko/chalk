import datetime as dt

import pytest
from docx import Document

from chalk.extractors._docx_schedule import format_week_label, parse_week_label
from chalk.extractors.docx_extractor import _extract_assessments


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Week 1 (8/24)", (1, 8, 24, "numeric")),
        ("Week 1 (Jan. 6)", (1, 1, 6, "abbr")),
        ("Week 3 (Sept 8)", (3, 9, 8, "abbr")),
        ("Week 3 (September 8)", (3, 9, 8, "full")),
        ("Week 14 (Apr. 7) – Final Presentations", (14, 4, 7, "abbr")),
    ],
)
def test_parse_week_label_accepts_numeric_and_month_name_dates(text, expected):
    label = parse_week_label(text)

    assert (label.week_number, label.month, label.day, label.month_style) == expected


def test_parse_week_label_ignores_a_parenthetical_that_is_not_a_date():
    assert parse_week_label("Week 3 (Online 2)") is None


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("Week 1 (8/24)", "Week 1 (1/11)"),
        ("Week 1 (Jan. 6)", "Week 1 (Jan. 11)"),
        ("Week 1 (Jan 6)", "Week 1 (Jan 11)"),
        ("Week 1 (January 6)", "Week 1 (January 11)"),
    ],
)
def test_format_week_label_keeps_the_original_style(original, expected):
    assert format_week_label(1, dt.date(2027, 1, 11), like=parse_week_label(original)) == expected


def test_headerless_grading_table_is_read_and_its_total_row_skipped():
    document = Document()
    table = document.add_table(rows=0, cols=2)
    for name, weight in [("Video Quizzes", "5 %"), ("Hands-on Labs", "25 %"), ("Group Project", "70 %"),
                         ("Total:", "100%")]:  # fmt: skip
        cells = table.add_row().cells
        cells[0].text, cells[1].text = name, weight

    assessments = _extract_assessments(document)

    assert [(a.name, a.weight) for a in assessments] == [
        ("Video Quizzes", 0.05),
        ("Hands-on Labs", 0.25),
        ("Group Project", 0.7),
    ]
