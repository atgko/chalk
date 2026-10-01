"""Unit tests for chalk.pdf_import.tables: which pdfplumber tables are
real, and stitching a schedule split across pages back together."""

from chalk.pdf_import.blocks import Paragraph, Table
from chalk.pdf_import.tables import RawTable, assemble, freeze, is_real_table, normalize_rows

HEADER = [[], ["Focus"], ["Assignment Due"]]


def _week(number, date, topic, due=None):
    return [[f"Week {number}", f"({date})"], [topic], [due] if due else []]


def _cells(table: Table, row: int) -> list[list[str]]:
    return [list(cell) for cell in table.rows[row]]


# ---- normalize_rows / is_real_table --------------------------------------------------


def test_normalize_drops_empty_rows_and_columns_and_placeholder_dashes():
    rows = [
        [["Week 1 (1/6)"], [], ["Intro"], ["–"]],
        [[], [], [], []],
        [["Week 2 (1/13)"], [], ["Charter"], ["Charter due"]],
    ]
    assert normalize_rows(rows) == [
        [["Week 1 (1/6)"], ["Intro"], []],
        [["Week 2 (1/13)"], ["Charter"], ["Charter due"]],
    ]
    assert normalize_rows([[[], []]]) == []


def test_ragged_rows_are_padded():
    assert normalize_rows([[["a"], ["b"]], [["c"]]]) == [[["a"], ["b"]], [["c"], []]]


def test_real_tables_are_schedules_or_mostly_filled_grids():
    schedule = [_week(1, "1/6", "Intro")]
    grading = [[["Activity"], ["Weight"]], [["Labs"], ["60%"]], [["Exam"], ["40%"]]]
    bullet_box = [[["● One"], []], [["●"], ["Two"]], [["● Three"], []]]
    one_column = [[["Just a boxed paragraph"]]]
    assert is_real_table(schedule)
    assert is_real_table(grading)
    assert not is_real_table(bullet_box)
    assert not is_real_table(one_column)
    assert not is_real_table([])


# ---- assemble -----------------------------------------------------------------------


def test_a_schedule_split_across_pages_becomes_one_table():
    page_one = freeze([HEADER, _week(1, "1/6", "Intro"), _week(2, "1/13", "Reporting and Issue")])
    # Page two: the header repeats, then the rest of week 2's row, then week 3.
    page_two = freeze([HEADER, [[], ["Management"], ["Status update"]], _week(3, "1/20", "Risk")])

    blocks = assemble([page_one, page_two])

    assert len(blocks) == 1
    table = blocks[0]
    assert [cell[0] if cell else "" for cell in _cells(table, 0)] == ["", "Focus", "Assignment Due"]
    assert _cells(table, 1)[0] == ["Week 1 (1/6)"]  # the label is one line
    assert _cells(table, 2) == [["Week 2 (1/13)"], ["Reporting and Issue Management"], ["Status update"]]
    assert _cells(table, 3)[0] == ["Week 3 (1/20)"]
    assert len(table.rows) == 4


def test_a_cut_off_paragraph_after_a_finished_one_stays_separate():
    page_one = freeze([HEADER, _week(1, "1/6", "Read: “Strategy”")])
    page_two = freeze([[[], ["Discussion Post"], []], _week(2, "1/13", "Charter")])
    blocks = assemble([page_one, page_two])
    assert _cells(blocks[0], 1)[1] == ["Read: “Strategy”", "Discussion Post"]


def test_module_titles_between_pieces_keep_one_table_per_module():
    module_two = freeze([HEADER, [[], ["Management"], []], _week(3, "1/20", "Scope")])
    blocks = assemble(
        [
            Paragraph("MODULE 1: Initiation", "heading"),
            freeze([HEADER, _week(1, "1/6", "Intro"), _week(2, "1/13", "Change")]),
            Paragraph("MODULE 2: Planning", "heading"),
            module_two,
        ]
    )
    assert [type(block) for block in blocks] == [Paragraph, Table, Paragraph, Table]
    # The cut-off row still belongs to week 2, in the first table.
    assert _cells(blocks[1], 2)[1] == ["Change Management"]
    assert _cells(blocks[3], 0)[1] == ["Focus"]
    assert _cells(blocks[3], 1)[0] == ["Week 3 (1/20)"]


def test_a_schedule_without_a_header_row_gets_one():
    blocks = assemble([freeze([_week(1, "1/6", "Intro")])])
    assert _cells(blocks[0], 0) == [["Week"], [], []]
    assert _cells(blocks[0], 1)[0] == ["Week 1 (1/6)"]


def test_a_top_of_page_box_continues_the_schedule_or_is_read_as_text():
    schedule = freeze([HEADER, _week(1, "1/6", "Project Status")])
    continuation = RawTable(((("",), ("Reporting",), ("Lab due",)),), is_real=False)
    blocks = assemble([schedule, continuation])
    assert _cells(blocks[0], 1)[1:] == [["Project Status Reporting"], ["Lab due"]]

    # Not after a schedule: just boxed text.
    box = RawTable(((("Office hours",), ("by appointment",)),), is_real=False)
    assert assemble([Paragraph("Intro"), box]) == [
        Paragraph("Intro"),
        Paragraph("Office hours"),
        Paragraph("by appointment"),
    ]


def test_other_real_tables_pass_through():
    grading = freeze([[["Activity"], ["Weight"]], [["Labs"], ["60%"]]])
    blocks = assemble([grading])
    assert blocks == [Table(((("Activity",), ("Weight",)), (("Labs",), ("60%",))))]
