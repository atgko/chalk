"""Points-based and percentage grading tables (chalk.extractors._grading),
read on their own and through both extractors."""

import pytest

from chalk.extractors import docx_extractor, markdown_extractor
from chalk.extractors._grading import header_column, headerless_points, parse_rows
from chalk.extractors.consistency import grading_weight_warning
from tests.fixtures import md_builder
from tests.fixtures.docx_builder import build_syllabus_with_grading_table


def weights(assessments) -> dict[str, float]:
    return {a.name: a.weight for a in assessments}


# ---- header_column / headerless_points -------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (["Assessment", "Weight"], (1, False)),
        (["Assessment", "%"], (1, False)),
        (["Assessment", "Points"], (1, True)),
        (["Item", "Pts"], (1, True)),
        (["Assessment", "Points", "Weight"], (2, False)),  # percentages win when both are given
        (["Assessment", "Due", "Possible points"], (2, True)),
        (["Assessment", "Notes"], None),
        (["Labs", "250 points"], None),  # a data row, not a header
        (["Points", "Labs"], None),  # the first column holds names
    ],
)
def test_header_column(header, expected):
    assert header_column(header) == expected


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([["Labs", "25%"], ["Exams", "75%"]], False),
        ([["Labs", "250 pts"], ["Exams", "750 points"]], True),
        ([["Labs", "250"], ["Exams", "750"]], None),  # bare numbers need a "Points" header
        ([["Week 1", "Intro"], ["Week 2", "Labs"]], None),
    ],
)
def test_headerless_points(rows, expected):
    assert headerless_points(rows) is expected


# ---- parse_rows ------------------------------------------------------------------------


def test_points_become_shares_of_the_total_row():
    rows = [["Labs", "250 pts"], ["Midterm", "150 pts"], ["Final", "600 pts"], ["Total", "1,000 pts"]]
    assert weights(parse_rows(rows, 1, points=True)) == {"Labs": 0.25, "Midterm": 0.15, "Final": 0.6}


def test_points_without_a_total_row_are_shares_of_their_sum():
    rows = [["Labs", "100"], ["Exams", "300"]]
    assert weights(parse_rows(rows, 1, points=True)) == {"Labs": 0.25, "Exams": 0.75}


def test_points_weights_round_to_a_hundredth_of_a_percent():
    rows = [["Labs", "100"], ["Exams", "250"]]
    assert weights(parse_rows(rows, 1, points=True)) == {"Labs": 0.2857, "Exams": 0.7143}


def test_a_row_missing_from_the_total_shows_up_as_weights_short_of_100_percent():
    rows = [["Labs", "250"], ["Final", "600"], ["Total", "1000"]]  # Midterm (150) wasn't listed
    assert sum(weights(parse_rows(rows, 1, points=True)).values()) == pytest.approx(0.85)


def test_points_cells_with_extra_text_read_the_points():
    rows = [["Labs", "250 pts (10 labs)"], ["Participation", "Up to 50 points"]]
    assert weights(parse_rows(rows, 1, points=True)) == {"Labs": 0.8333, "Participation": 0.1667}


def test_points_rows_without_a_number_are_skipped():
    rows = [["Labs", "200"], ["Extra credit", "varies"], ["Exams", "200"]]
    assert weights(parse_rows(rows, 1, points=True)) == {"Labs": 0.5, "Exams": 0.5}


def test_points_table_with_no_readable_points_has_no_assessments():
    assert parse_rows([["Labs", "TBD"], ["Total", "0"]], 1, points=True) == []


def test_percentages_skip_the_total_row():
    rows = [["Labs", "40%"], ["Exams", "60%"], ["Total", "100%"]]
    assert weights(parse_rows(rows, 1, points=False)) == {"Labs": 0.4, "Exams": 0.6}


# ---- Word ------------------------------------------------------------------------------


def test_word_points_table_with_a_header(tmp_path):
    path = build_syllabus_with_grading_table(
        tmp_path / "syllabus.docx",
        [("Hands-on Labs", "250"), ("Video Quizzes", "50"), ("Final Project", "200"), ("Total", "500")],
    )
    course_data = docx_extractor.extract_course_data(path)
    assert weights(course_data.assessments) == {"Hands-on Labs": 0.5, "Video Quizzes": 0.1, "Final Project": 0.4}
    assert grading_weight_warning(course_data) is None


def test_word_points_table_without_a_header(tmp_path):
    path = build_syllabus_with_grading_table(
        tmp_path / "syllabus.docx", [("Labs — 10 × 25", "250 pts"), ("Exams", "750 pts")], header=None
    )
    assert weights(docx_extractor.extract_course_data(path).assessments) == {"Labs — 10 × 25": 0.25, "Exams": 0.75}


def test_word_table_with_points_and_weight_columns_reads_the_weights(tmp_path):
    path = build_syllabus_with_grading_table(
        tmp_path / "syllabus.docx",
        [("Labs", "250", "30%"), ("Exams", "750", "70%")],
        header=("Assessment", "Points", "Weight"),
    )
    assert weights(docx_extractor.extract_course_data(path).assessments) == {"Labs": 0.3, "Exams": 0.7}


def test_word_points_table_missing_a_row_warns_on_review(tmp_path):
    path = build_syllabus_with_grading_table(
        tmp_path / "syllabus.docx", [("Labs", "250 pts"), ("Final", "600 pts"), ("Total", "1000 pts")]
    )
    warning = grading_weight_warning(docx_extractor.extract_course_data(path))
    assert "add up to 85%" in warning
    assert "Total row" in warning


# ---- Markdown --------------------------------------------------------------------------


def build_markdown_with_grading(tmp_path, table: str):
    path = md_builder.build_minimal_syllabus(tmp_path / "syllabus.md")
    text = path.read_text(encoding="utf-8")
    old = "| Assessment | Weight |\n| --- | --- |\n| Quizzes | 10% |\n| Final Project | 30% |\n"
    assert old in text
    path.write_text(text.replace(old, table), encoding="utf-8")
    return path


def test_markdown_points_table(tmp_path):
    path = build_markdown_with_grading(
        tmp_path,
        "| Assessment | Points |\n| --- | --- |\n| Quizzes | 100 |\n| Final Project | 300 |\n| Total | 400 |\n",
    )
    assert weights(markdown_extractor.extract_course_data(path).assessments) == {"Quizzes": 0.25, "Final Project": 0.75}


def test_markdown_percent_table_no_longer_lists_its_total_row(tmp_path):
    path = build_markdown_with_grading(
        tmp_path, "| Assessment | Weight |\n| --- | --- |\n| Quizzes | 40% |\n| Exams | 60% |\n| Total | 100% |\n"
    )
    assert weights(markdown_extractor.extract_course_data(path).assessments) == {"Quizzes": 0.4, "Exams": 0.6}
