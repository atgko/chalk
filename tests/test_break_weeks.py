"""Moving weeks past a break the class takes off (Nov 9 UAT: the Fall →
Spring rollover warned that Week 9 fell in Spring Break, but the new
syllabus still had class that week and no Spring Break)."""

import datetime as dt

from docx import Document

from chalk.models import Week
from chalk.pipeline import (
    confirm_rollover,
    extract_syllabus,
    preview_rollover,
    save_reviewed_course,
)
from chalk.rollover.break_weeks import (
    SkippedBreak,
    break_rows_for,
    has_numbered_break_weeks,
    past_term_end_flag,
    plan_week_starts,
)
from chalk.rollover.preview import roll_over_course
from tests.test_rollover_preview import CALENDARS, _is6640_ten_week_course

MON, TUE, WED, THU = 0, 1, 2, 3
SPRING_BREAK = {"label": "Spring Break", "date_start": "2027-03-06", "date_end": "2027-03-14"}
THANKSGIVING = {"label": "Thanksgiving Break", "date_start": "2027-11-25", "date_end": "2027-11-28"}


# ---- Laying out the weeks ----------------------------------------------------------


def test_a_break_covering_a_whole_week_moves_that_week_and_the_later_ones():
    starts, skipped = plan_week_starts([8, 9, 10], dt.date(2027, 1, 11), [SPRING_BREAK], (WED,))

    # Week 8 starts Mar 1; Week 9 would start Mar 8, inside Spring Break.
    assert starts == {8: dt.date(2027, 3, 1), 9: dt.date(2027, 3, 15), 10: dt.date(2027, 3, 22)}
    assert skipped == [SkippedBreak(SPRING_BREAK, 9)]


def test_a_break_covering_only_some_class_days_doesnt_move_anything():
    # Thanksgiving Break (Thu-Sun) on a Tue/Thu class: Tuesday still meets.
    starts, skipped = plan_week_starts([14], dt.date(2027, 8, 23), [THANKSGIVING], (TUE, THU))

    assert starts == {14: dt.date(2027, 11, 22)}
    assert skipped == []


def test_a_thursday_class_steps_over_thanksgiving():
    _, skipped = plan_week_starts([14], dt.date(2027, 8, 23), [THANKSGIVING], (THU,))

    assert skipped == [SkippedBreak(THANKSGIVING, 14)]


def test_without_meeting_days_a_break_must_cover_every_weekday():
    _, spring = plan_week_starts([9], dt.date(2027, 1, 11), [SPRING_BREAK], ())
    _, thanksgiving = plan_week_starts([14], dt.date(2027, 8, 23), [THANKSGIVING], ())

    assert spring == [SkippedBreak(SPRING_BREAK, 9)]
    assert thanksgiving == []


def test_a_numbered_break_week_is_its_own_slot():
    weeks = [Week(week_number=10, date=dt.date(2026, 3, 10), label="Week 10 (3/10)", is_break=False, topics=["Spring Break"])]

    assert has_numbered_break_weeks(weeks)
    assert not has_numbered_break_weeks(_is6640_ten_week_course().weeks)


def test_break_rows_are_added_once_and_not_for_a_break_already_shown():
    skipped = [SkippedBreak(SPRING_BREAK, 9), SkippedBreak(SPRING_BREAK, 9)]
    shown = Week(label="Spring Break", is_break=True, date_start=dt.date(2027, 3, 6), date_end=dt.date(2027, 3, 14))

    assert [week.label for week in break_rows_for(skipped, [])] == ["Spring Break (3/6 - 3/14)"]
    assert break_rows_for(skipped, [shown]) == []


def test_a_week_moved_past_the_terms_end_is_flagged():
    weeks = [Week(week_number=16, date=dt.date(2027, 12, 15), label="Week 16", is_break=False)]

    flag = past_term_end_flag(weeks, dt.date(2027, 12, 9), "Fall 2027")

    assert flag.startswith("Week 16 (Dec 15) is after Fall 2027 ends (Dec 9).")
    assert past_term_end_flag(weeks, dt.date(2027, 12, 20), "Fall 2027") is None


# ---- Through a rollover ----------------------------------------------------------


def _rolled(**kwargs):
    return roll_over_course(_is6640_ten_week_course(), target_term="Fall 2027", calendars=CALENDARS, **kwargs)


def test_the_weeks_move_past_a_break_that_covers_a_whole_week():
    # Nov 10 UAT: always, not an option ("can't we assume this will always be the case?").
    course, preview = _rolled(meeting_days=(WED,))

    dates = {week.week_number: week.date for week in course.weeks if not week.is_break}
    assert dates[7] == dt.date(2027, 10, 6) and dates[8] == dt.date(2027, 10, 20)
    assert any("so Week 8 and the weeks after it move a week later" in flag for flag in preview.general_flags)
    assert not any("confirm Week 8 timing" in flag for flag in preview.week_flags())


def test_a_break_the_class_meets_through_never_moves_weeks():
    course, _ = _rolled(meeting_days=(WED,), breaks_not_observed=frozenset({"Fall Break"}))

    assert next(week for week in course.weeks if week.week_number == 8).date == dt.date(2027, 10, 13)


# ---- The written syllabus --------------------------------------------------------


def _syllabus_without_break_rows(path):
    document = Document()
    for line in ("Course: IS 6640 Networking and Servers", "Term: Fall 2026"):
        document.add_paragraph(line)
    dates = [dt.date(2026, 8, 26) + dt.timedelta(days=7 * (n - 1)) for n in range(1, 11)]
    rows = [("Week", "Topics")] + [
        (f"Week {n} ({day.month}/{day.day})", f"Topic {n}") for n, day in enumerate(dates, start=1)
    ]
    table = document.add_table(rows=len(rows), cols=2)
    for row, (label, topic) in zip(table.rows, rows, strict=True):
        row.cells[0].text, row.cells[1].text = label, topic
    document.save(str(path))
    return path


def test_a_schedule_with_no_break_rows_gets_one_for_the_break_it_moved_past(tmp_project, tmp_path):
    course_data, _ = extract_syllabus(tmp_project, _syllabus_without_break_rows(tmp_path / "s.docx"))
    save_reviewed_course(tmp_project, course_data)

    plan = preview_rollover(
        tmp_project, course_data, "Spring 2027", llm_generate_topics=False, meeting_days=(WED,)
    )
    confirm_rollover(tmp_project, plan)

    table = Document(str(tmp_project.syllabus_output("word"))).tables[0]
    labels = [row.cells[0].text for row in table.rows]
    spring = next(i for i, label in enumerate(labels) if label.startswith("Spring Break ("))
    assert labels[spring - 1].startswith("Week 8 (") and labels[spring + 1].startswith("Week 9 (")
    assert table.rows[spring].cells[1].text == "No class"


# ---- Holidays the old term had, still named in the syllabus ------------------------


def test_lines_naming_last_terms_holidays_are_listed_with_the_new_terms(tmp_project, tmp_path):
    path = _syllabus_without_break_rows(tmp_path / "s.docx")
    document = Document(str(path))
    document.add_paragraph("No class on Labor Day; the lab is closed over Thanksgiving.")
    document.add_paragraph("Fall Break: catch up on the readings.")
    document.add_paragraph("Labs are due on Sundays.")
    document.save(str(path))
    course_data, _ = extract_syllabus(tmp_project, path)

    plan = preview_rollover(tmp_project, course_data, "Spring 2027", llm_generate_topics=False)

    flag = next(flag for flag in plan.preview.general_flags if flag.startswith("These lines still mention"))
    assert flag.startswith("These lines still mention Labor Day or Fall Break, which Spring 2027 doesn't have:")
    assert '"No class on Labor Day; the lab is closed over Thanksgiving."' in flag
    assert '"Fall Break: catch up on the readings."' in flag
    assert "Labs are due" not in flag
    assert "Martin Luther King Jr. Day (Jan 18)" in flag and "Spring Break (Mar 6 – Mar 14)" in flag


def test_a_same_season_rollover_has_nothing_to_list(tmp_project, tmp_path):
    path = _syllabus_without_break_rows(tmp_path / "s.docx")
    document = Document(str(path))
    document.add_paragraph("No class on Labor Day.")
    document.save(str(path))
    course_data, _ = extract_syllabus(tmp_project, path)

    plan = preview_rollover(tmp_project, course_data, "Fall 2027", llm_generate_topics=False)

    assert not any(flag.startswith("These lines still mention") for flag in plan.preview.general_flags)
