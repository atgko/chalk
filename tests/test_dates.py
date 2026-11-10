"""Tests for chalk.extractors._dates.roll_dates_past_new_year: schedule
rows are read with the term's year, and a schedule that crosses New Year
needs the next year for its later dates."""

import datetime as dt

from chalk.extractors import markdown_extractor
from chalk.extractors._dates import roll_dates_past_new_year
from chalk.models import Week
from tests.fixtures import md_builder


def _week(number: int, month: int, day: int, year: int = 2026) -> Week:
    return Week(week_number=number, date=dt.date(year, month, day), label=f"Week {number}")


def _break(start: tuple[int, int], end: tuple[int, int], year: int = 2026) -> Week:
    return Week(
        date_start=dt.date(year, *start), date_end=dt.date(year, *end), label="Winter Break", is_break=True
    )


def test_a_fall_schedule_inside_one_year_is_unchanged():
    weeks = [_week(1, 8, 24), _week(2, 10, 19), _week(3, 12, 7)]
    assert roll_dates_past_new_year(weeks) == weeks


def test_a_january_row_after_december_gets_the_next_year():
    rolled = roll_dates_past_new_year([_week(15, 12, 7), _week(16, 12, 14), _week(17, 1, 4)])
    assert [week.date for week in rolled] == [dt.date(2026, 12, 7), dt.date(2026, 12, 14), dt.date(2027, 1, 4)]


def test_every_row_after_the_crossing_keeps_the_next_year():
    rolled = roll_dates_past_new_year([_week(1, 12, 14), _week(2, 1, 4), _week(3, 1, 11)])
    assert [week.date.year for week in rolled] == [2026, 2027, 2027]


def test_a_break_that_spans_new_year_ends_in_the_next_year():
    rolled = roll_dates_past_new_year([_week(15, 12, 14), _break((12, 20), (1, 3)), _week(16, 1, 4)])
    assert (rolled[1].date_start, rolled[1].date_end) == (dt.date(2026, 12, 20), dt.date(2027, 1, 3))
    assert rolled[2].date == dt.date(2027, 1, 4)


def test_slightly_out_of_order_rows_are_not_treated_as_a_new_year():
    # A break row listed just after the week it falls in.
    weeks = [_week(7, 10, 19), _break((10, 10), (10, 18))]
    assert roll_dates_past_new_year(weeks) == weeks


def test_a_markdown_fall_syllabus_with_a_january_finals_week_is_extracted_with_the_next_year(tmp_path):
    path = md_builder.build_minimal_syllabus(tmp_path / "s.md")
    text = path.read_text(encoding="utf-8").replace(
        "| 2 | 10/19 - 10/25 | Networking Basics | Lab 1 Due |\n",
        "| 2 | 10/19 - 10/25 | Networking Basics | Lab 1 Due |\n| 3 | 1/4 - 1/8 | Finals | Final Due |\n",
    )
    path.write_text(text, encoding="utf-8")

    weeks = markdown_extractor.extract_course_data(path).weeks

    assert next(week for week in weeks if week.week_number == 3).date == dt.date(2027, 1, 4)


def test_a_spring_schedule_with_a_december_row_puts_that_row_in_the_year_before():
    # A Spring 2027 orientation "Week 0 (12/15)" is read with the term's year.
    weeks = [_week(0, 12, 15, 2027), _week(1, 1, 12, 2027), _week(2, 1, 19, 2027)]

    rolled = roll_dates_past_new_year(weeks, spring_term=True)

    assert [week.date for week in rolled] == [dt.date(2026, 12, 15), dt.date(2027, 1, 12), dt.date(2027, 1, 19)]


def test_a_spring_schedule_without_a_december_row_is_unchanged():
    weeks = [_week(1, 1, 12, 2027), _week(16, 5, 4, 2027)]
    assert roll_dates_past_new_year(weeks, spring_term=True) == weeks


def test_a_markdown_spring_syllabus_with_a_december_week_0_keeps_the_term_year(tmp_path):
    path = tmp_path / "s.md"
    path.write_text(
        "Course: IS 4490 Emerging Technologies\n"
        "Term: Spring 2027\n"
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 0 | 12/15 - 12/19 | Orientation |  |\n"
        "| 1 | 1/11 - 1/17 | Course Introduction | Reading 1 Due |\n"
        "| 2 | 1/18 - 1/24 | Networking Basics | Lab 1 Due |\n",
        encoding="utf-8",
    )

    weeks = markdown_extractor.extract_course_data(path).weeks

    by_number = {week.week_number: week.date for week in weeks}
    assert by_number[0] == dt.date(2026, 12, 15)
    assert by_number[1] == dt.date(2027, 1, 11)
    assert by_number[2] == dt.date(2027, 1, 18)
