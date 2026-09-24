"""Tests for chalk.rollover.preview, validated against the PRD's own
worked example (section 6.2): IS 6640, 10 weeks, Fall 2026 -> Fall 2027.
"""

import datetime as dt

import pytest

from chalk.errors import LLMProviderError
from chalk.models import CourseData, CourseInfo, UniversityDate, Week
from chalk.rollover.preview import roll_over_course

CALENDARS = {
    "terms": [
        {
            "term": "Fall 2026",
            "start": "2026-08-24",
            "end": "2026-12-10",
            "no_class_dates": [
                {"label": "Labor Day", "date": "2026-09-07"},
                {"label": "Fall Break", "date_start": "2026-10-10", "date_end": "2026-10-18"},
                {
                    "label": "Thanksgiving Break",
                    "date_start": "2026-11-26",
                    "date_end": "2026-11-29",
                },
            ],
        },
        {
            "term": "Fall 2027",
            "start": "2027-08-23",
            "end": "2027-12-09",
            "no_class_dates": [
                {"label": "Labor Day", "date": "2027-09-06"},
                {"label": "Fall Break", "date_start": "2027-10-09", "date_end": "2027-10-17"},
                {
                    "label": "Thanksgiving Break",
                    "date_start": "2027-11-25",
                    "date_end": "2027-11-28",
                },
            ],
        },
    ]
}


def _is6640_ten_week_course(source_format: str = "word") -> CourseData:
    term_start = dt.date(2026, 8, 24)
    weeks = []
    for week_number in range(1, 11):
        week_date = term_start + dt.timedelta(days=7 * (week_number - 1))
        weeks.append(
            Week(
                week_number=week_number,
                date=week_date,
                label=f"Week {week_number} ({week_date.month}/{week_date.day})",
                is_break=False,
                topics=[f"Topic {week_number}"],
                assignments=[f"Lab {week_number} Due"] if week_number != 10 else [],
            )
        )
    weeks.append(
        Week(
            week_number=None,
            date_start=dt.date(2026, 10, 10),
            date_end=dt.date(2026, 10, 18),
            label="Fall Break",
            is_break=True,
        )
    )
    weeks.sort(key=lambda w: w.date if w.date else w.date_start)

    return CourseData(
        course=CourseInfo(
            title="IS 6640 Networking and Servers",
            number="IS 6640",
            section="090",
            credits=3,
            term="Fall 2026",
            term_start=term_start,
            term_end=dt.date(2026, 10, 26),
            duration_weeks=10,
            meeting_pattern="Online async",
            instructor="Dave Norwood",
            source_format=source_format,
            source_file="source/syllabus.docx",
            extracted_at=dt.datetime(2026, 9, 17, tzinfo=dt.timezone.utc),
        ),
        weeks=weeks,
    )


def test_reproduces_the_prd_worked_example_exactly():
    course_data = _is6640_ten_week_course()

    new_course_data, preview = roll_over_course(
        course_data, target_term="Fall 2027", calendars=CALENDARS
    )

    assert new_course_data.course.term == "Fall 2027"
    assert new_course_data.course.term_start == dt.date(2027, 8, 23)
    assert new_course_data.course.duration_weeks == 10

    changes_by_week = {
        c.week_number: c for c in preview.week_changes if c.week_number is not None
    }
    assert changes_by_week[1].new_date == dt.date(2027, 8, 23)
    assert changes_by_week[2].new_date == dt.date(2027, 8, 30)
    assert changes_by_week[3].new_date == dt.date(2027, 9, 6)
    assert changes_by_week[7].new_date == dt.date(2027, 10, 4)

    week8_flags = changes_by_week[8].flags
    assert len(week8_flags) == 1
    assert "Fall Break 2027 is Oct 9–17" in week8_flags[0]
    assert "confirm Week 8 timing" in week8_flags[0]

    # Week 9's rolled-over date (Oct 18) falls just outside the Oct 9-17
    # break window.
    assert changes_by_week[9].flags == []


def _with_university_dates(course_data: CourseData) -> CourseData:
    return course_data.model_copy(
        update={
            "university_dates": [
                UniversityDate(event="Classes begin", date=dt.date(2026, 8, 24)),
                UniversityDate(
                    event="Fall Break", date_start=dt.date(2026, 10, 10), date_end=dt.date(2026, 10, 18)
                ),
                UniversityDate(event="Classes end", date=dt.date(2026, 10, 26)),
            ]
        }
    )


def test_university_dates_begin_and_end_use_the_target_terms_start_and_end():
    course_data = _with_university_dates(_is6640_ten_week_course())

    new_course_data, _preview = roll_over_course(
        course_data, target_term="Fall 2027", calendars=CALENDARS
    )

    dates_by_event = {d.event: d for d in new_course_data.university_dates}
    assert dates_by_event["Classes begin"].date == dt.date(2027, 8, 23)
    assert dates_by_event["Classes end"].date == dt.date(2027, 12, 9)


def test_university_dates_break_entry_matches_the_target_calendar():
    course_data = _with_university_dates(_is6640_ten_week_course())

    new_course_data, _preview = roll_over_course(
        course_data, target_term="Fall 2027", calendars=CALENDARS
    )

    dates_by_event = {d.event: d for d in new_course_data.university_dates}
    fall_break = dates_by_event["Fall Break"]
    assert fall_break.date_start == dt.date(2027, 10, 9)
    assert fall_break.date_end == dt.date(2027, 10, 17)


def test_university_date_with_no_match_falls_back_to_offset_shift():
    course_data = _is6640_ten_week_course()
    course_data = course_data.model_copy(
        update={
            "university_dates": [
                UniversityDate(event="Add/drop deadline", date=dt.date(2026, 9, 4)),
            ]
        }
    )

    new_course_data, _preview = roll_over_course(
        course_data, target_term="Fall 2027", calendars=CALENDARS
    )

    # Term start shifted by 364 days (Aug 24 2026 -> Aug 23 2027 is 364
    # days, one less than the 365-day "same calendar date next year"),
    # so an unmatched date shifts by that same offset: Sep 4 2026 + 364
    # days = Sep 3 2027.
    assert new_course_data.university_dates[0].date == dt.date(2027, 9, 3)


def test_university_date_range_with_no_match_falls_back_to_offset_shift():
    course_data = _is6640_ten_week_course()
    course_data = course_data.model_copy(
        update={
            "university_dates": [
                UniversityDate(
                    event="Registration window",
                    date_start=dt.date(2026, 9, 1),
                    date_end=dt.date(2026, 9, 5),
                ),
            ]
        }
    )

    new_course_data, _preview = roll_over_course(
        course_data, target_term="Fall 2027", calendars=CALENDARS
    )

    entry = new_course_data.university_dates[0]
    assert entry.date_start == dt.date(2027, 8, 31)
    assert entry.date_end == dt.date(2027, 9, 4)


def test_break_week_uses_the_target_terms_own_calendar_dates():
    course_data = _is6640_ten_week_course()

    new_course_data, _preview = roll_over_course(
        course_data, target_term="Fall 2027", calendars=CALENDARS
    )

    break_week = next(week for week in new_course_data.weeks if week.is_break)
    assert break_week.date_start == dt.date(2027, 10, 9)
    assert break_week.date_end == dt.date(2027, 10, 17)
    # The label's embedded date text must be refreshed too, not left
    # showing the source term's dates.
    assert break_week.label == "Fall Break (10/9 - 10/17)"


def test_no_duration_change_means_no_general_flag():
    course_data = _is6640_ten_week_course()

    _new_course_data, preview = roll_over_course(
        course_data, target_term="Fall 2027", calendars=CALENDARS
    )

    assert preview.general_flags == []


def test_shrinking_duration_drops_trailing_weeks():
    course_data = _is6640_ten_week_course()

    new_course_data, preview = roll_over_course(
        course_data, target_term="Fall 2027", calendars=CALENDARS, target_duration_weeks=5
    )

    regular_weeks = [week for week in new_course_data.weeks if not week.is_break]
    assert len(regular_weeks) == 5
    assert new_course_data.course.duration_weeks == 5
    assert "10 to 5 weeks" in preview.general_flags[0]


def test_expanding_duration_drafts_placeholder_topics_via_llm(monkeypatch):
    course_data = _is6640_ten_week_course()

    monkeypatch.setattr(
        "chalk.rollover.preview.complete",
        lambda prompt, max_tokens=100: {
            "text": "Advanced Topics\nCapstone Wrap-up",
            "input_tokens": 20,
            "output_tokens": 10,
        },
    )

    new_course_data, preview = roll_over_course(
        course_data, target_term="Fall 2027", calendars=CALENDARS, target_duration_weeks=12
    )

    regular_weeks = sorted(
        (week for week in new_course_data.weeks if not week.is_break),
        key=lambda week: week.week_number,
    )
    assert len(regular_weeks) == 12
    week11 = regular_weeks[10]
    assert week11.topics == ["Advanced Topics", "Capstone Wrap-up"]
    assert "AI-generated draft" in week11.notes
    assert "10 to 12 weeks" in preview.general_flags[0]


def test_expanding_duration_degrades_gracefully_when_llm_unavailable(monkeypatch):
    course_data = _is6640_ten_week_course()

    def _boom(prompt, max_tokens=100):
        raise LLMProviderError("Could not reach the LLM provider.")

    monkeypatch.setattr("chalk.rollover.preview.complete", _boom)

    new_course_data, _preview = roll_over_course(
        course_data, target_term="Fall 2027", calendars=CALENDARS, target_duration_weeks=11
    )

    regular_weeks = sorted(
        (week for week in new_course_data.weeks if not week.is_break),
        key=lambda week: week.week_number,
    )
    week11 = regular_weeks[10]
    assert week11.topics == []
    assert "No LLM available" in week11.notes


def test_term_not_in_calendar_falls_back_to_manual_week1_date():
    course_data = _is6640_ten_week_course()

    new_course_data, preview = roll_over_course(
        course_data,
        target_term="Fall 2099",
        calendars=CALENDARS,
        manual_week1_date=dt.date(2099, 8, 20),
    )

    assert new_course_data.course.term_start == dt.date(2099, 8, 20)
    assert all(c.flags == [] for c in preview.week_changes if c.week_number is not None)


def test_term_not_in_calendar_and_no_manual_date_raises():
    course_data = _is6640_ten_week_course()

    with pytest.raises(ValueError):
        roll_over_course(course_data, target_term="Fall 2099", calendars=CALENDARS)


def test_dst_boundary_flag_only_applies_to_markdown_source_format():
    course_data = _is6640_ten_week_course(source_format="markdown")
    course_data = _give_week_ten_an_assignment(course_data)

    _new_course_data, preview = roll_over_course(
        course_data, target_term="Fall 2027", calendars=CALENDARS
    )

    changes_by_week = {
        c.week_number: c for c in preview.week_changes if c.week_number is not None
    }
    dst_flags = [flag for flag in changes_by_week[10].flags if "DST boundary" in flag]
    assert len(dst_flags) == 1


def test_dst_boundary_flag_does_not_apply_to_word_source_format():
    course_data = _is6640_ten_week_course(source_format="word")
    course_data = _give_week_ten_an_assignment(course_data)

    _new_course_data, preview = roll_over_course(
        course_data, target_term="Fall 2027", calendars=CALENDARS
    )

    changes_by_week = {
        c.week_number: c for c in preview.week_changes if c.week_number is not None
    }
    dst_flags = [flag for flag in changes_by_week[10].flags if "DST boundary" in flag]
    assert dst_flags == []


def _give_week_ten_an_assignment(course_data: CourseData) -> CourseData:
    # Week 10's rolled-over date (Oct 25, 2027) sits within two weeks of
    # the first Sunday of November 2027 either way, so this reliably puts
    # week 10 inside the DST-flag window without depending on exactly
    # which day that Sunday falls on.
    weeks = [
        week.model_copy(update={"assignments": ["Final Project Due"]})
        if week.week_number == 10
        else week
        for week in course_data.weeks
    ]
    return course_data.model_copy(update={"weeks": weeks})
