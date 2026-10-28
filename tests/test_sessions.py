"""Course sessions (chalk/sessions.py): a term split into three 5-week
blocks, a 1.5-credit course being one of them."""

import datetime as dt

import pytest

from chalk.extractors._front_matter import extract_front_matter
from chalk.extractors.consistency import check_term_consistency
from chalk.sessions import (
    FULL_TERM,
    SessionSpan,
    available_spans,
    guess_session,
    parse_session,
    session_start,
)

FALL_2026 = {
    "term": "Fall 2026",
    "start": "2026-08-24",
    "end": "2026-12-10",
    "no_class_dates": [
        {"label": "Labor Day", "date": "2026-09-07"},
        {"label": "Fall Break", "date_start": "2026-10-10", "date_end": "2026-10-18"},
        {"label": "Thanksgiving Break", "date_start": "2026-11-26", "date_end": "2026-11-29"},
    ],
}
SUMMER_2027 = {"term": "Summer 2027", "start": "2027-05-17", "end": "2027-08-04", "no_class_dates": []}


def test_sessions_are_five_class_weeks_apart_skipping_fall_break():
    assert session_start(FALL_2026, 1) == dt.date(2026, 8, 24)
    assert session_start(FALL_2026, 2) == dt.date(2026, 9, 28)
    # 5 more class weeks: Sep 28, Oct 5, (Fall Break), Oct 19, Oct 26, Nov 2.
    assert session_start(FALL_2026, 3) == dt.date(2026, 11, 9)


def test_a_session_never_starts_inside_a_break():
    term = {**FALL_2026, "no_class_dates": [{"label": "Break", "date_start": "2026-09-26", "date_end": "2026-10-04"}]}
    assert session_start(term, 2) == dt.date(2026, 10, 5)


def test_spans_know_their_length_label_and_code():
    assert SessionSpan(2, 3).weeks == 10
    assert SessionSpan(2, 3).label == "Sessions 2–3 (10 weeks)"
    assert SessionSpan(1, 1).label == "Session 1 (5 weeks)"
    assert FULL_TERM.label == "Full term (Sessions 1–3)" and FULL_TERM.weeks == 15
    assert parse_session("2-3") == SessionSpan(2, 3) and parse_session("2–3") == SessionSpan(2, 3)
    assert parse_session(" 3 ") == SessionSpan(3, 3)


def test_an_unknown_session_is_an_error():
    with pytest.raises(ValueError, match="isn't a session"):
        parse_session("4")


def test_a_summer_term_offers_10_or_12_weeks_not_sessions():
    spans = available_spans(SUMMER_2027)
    assert [(span.label, span.weeks) for span in spans] == [("Full summer term (12 weeks)", 12), ("10 weeks", 10)]
    assert not any(span.is_full_term for span in spans)  # each one sets the course's length
    assert all(session_start(SUMMER_2027, span.first) == dt.date(2027, 5, 17) for span in spans)
    assert len(available_spans(FALL_2026)) == 6


def test_a_semester_term_drops_a_session_that_runs_past_its_end():
    short = {**FALL_2026, "end": "2026-11-20"}
    assert SessionSpan(3, 3) not in available_spans(short) and FULL_TERM in available_spans(short)


@pytest.mark.parametrize(
    ("weeks", "credits", "expected"),
    [
        (15, 3, FULL_TERM),
        (10, 3, SessionSpan(1, 2)),
        (5, 3, SessionSpan(1, 1)),
        (15, 1.5, SessionSpan(1, 1)),  # a 1.5-credit course is one 5-week sprint
        (2, None, FULL_TERM),  # an odd length keeps the course's own length
        (16, None, FULL_TERM),
    ],
)
def test_guess_session(weeks, credits, expected):
    assert guess_session(weeks, credits) == expected


@pytest.mark.parametrize(("weeks", "expected"), [(10, 10), (8, 10), (12, 12), (15, 12)])
def test_guess_summer_length(weeks, expected):
    assert guess_session(weeks, 3, summer=True).weeks == expected


def test_one_and_a_half_credits_are_read_as_such():
    assert extract_front_matter(["Term: Fall 2026", "Credits: 1.5"])["credits"] == 1.5
    assert extract_front_matter(["IS 6490 | Fall 2026", "1.5 Credit Hours"])["credits"] == 1.5  # not 5
    assert extract_front_matter(["Term: Fall 2026", "Credits: 3"])["credits"] == 3


def test_a_course_starting_in_session_3_passes_the_term_check():
    from tests.sample_course import build_sample_course_data

    course_data = build_sample_course_data()
    weeks = [
        week.model_copy(update={"date": dt.date(2026, 11, 9)}) if week.week_number == 1 else week
        for week in course_data.weeks
    ]
    course = course_data.course.model_copy(update={"term": "Fall 2026"})
    assert check_term_consistency(course_data.model_copy(update={"weeks": weeks, "course": course})).passed
