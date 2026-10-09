"""Tests for rolling a course over into a *different* season (e.g. Fall ->
Spring), where the source syllabus's named breaks don't exist in the
target term. Break rows are rebuilt from the target term's own calendar
instead of carrying the old names forward (teammate feedback: Spring
rollovers kept showing "Fall Break").
"""

import datetime as dt

from chalk.models import CourseData, CourseInfo, UniversityDate, Week
from chalk.rollover.preview import roll_over_course

CALENDARS = {
    "terms": [
        {
            "term": "Spring 2027",
            "start": "2027-01-11",
            "end": "2027-04-27",
            "no_class_dates": [
                {"label": "Martin Luther King Jr. Day", "date": "2027-01-18"},
                {"label": "Spring Break", "date_start": "2027-03-06", "date_end": "2027-03-14"},
            ],
        },
        {
            "term": "Summer 2027",
            "start": "2027-05-17",
            "end": "2027-08-04",
            "no_class_dates": [{"label": "Memorial Day", "date": "2027-05-31"}],
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


def _course(
    *,
    term: str,
    term_start: dt.date,
    weeks_count: int,
    breaks: list[tuple[str, dt.date, dt.date]],
    university_dates: list[UniversityDate] | None = None,
) -> CourseData:
    weeks = [
        Week(
            week_number=n,
            date=term_start + dt.timedelta(days=7 * (n - 1)),
            label=f"Week {n}",
            topics=[f"Topic {n}"],
        )
        for n in range(1, weeks_count + 1)
    ]
    weeks += [
        Week(label=label, is_break=True, date_start=start, date_end=end)
        for label, start, end in breaks
    ]
    weeks.sort(key=lambda w: w.date or w.date_start)
    return CourseData(
        course=CourseInfo(
            title="Networking and Servers",
            number="IS 6640",
            section="090",
            credits=3,
            term=term,
            term_start=term_start,
            term_end=weeks[-1].date or weeks[-1].date_end,
            duration_weeks=weeks_count,
            meeting_pattern="Online async",
            instructor="Dave Norwood",
            source_format="word",
            source_file="source/syllabus.docx",
            extracted_at=dt.datetime(2026, 9, 30, tzinfo=dt.timezone.utc),
        ),
        weeks=weeks,
        university_dates=university_dates or [],
    )


def _fall_2026_course(**overrides) -> CourseData:
    kwargs = {
        "term": "Fall 2026",
        "term_start": dt.date(2026, 8, 24),
        "weeks_count": 10,
        "breaks": [("Fall Break (10/10 - 10/18)", dt.date(2026, 10, 10), dt.date(2026, 10, 18))],
    }
    kwargs.update(overrides)
    return _course(**kwargs)


def _break_labels(course_data: CourseData) -> list[str]:
    return [week.label for week in course_data.weeks if week.is_break]


def test_fall_to_spring_replaces_fall_break_with_spring_break():
    new_course_data, _ = roll_over_course(
        _fall_2026_course(), target_term="Spring 2027", calendars=CALENDARS
    )

    breaks = [week for week in new_course_data.weeks if week.is_break]
    assert [week.label for week in breaks] == ["Spring Break (3/6 - 3/14)"]
    assert (breaks[0].date_start, breaks[0].date_end) == (dt.date(2027, 3, 6), dt.date(2027, 3, 14))


def test_fall_to_spring_places_the_new_break_in_date_order():
    new_course_data, _ = roll_over_course(
        _fall_2026_course(), target_term="Spring 2027", calendars=CALENDARS
    )

    labels = [week.label for week in new_course_data.weeks]
    # Week 8 starts Mar 1, Week 9 starts Mar 8 (inside the break, so flagged).
    assert (
        labels.index("Week 8 (3/1)")
        < labels.index("Spring Break (3/6 - 3/14)")
        < labels.index("Week 9 (3/8)")
    )


def test_fall_to_spring_preview_explains_the_break_replacement():
    _, preview = roll_over_course(
        _fall_2026_course(), target_term="Spring 2027", calendars=CALENDARS
    )

    assert any("Fall Break" in flag and "Spring Break" in flag for flag in preview.general_flags)
    break_changes = [change for change in preview.week_changes if change.week_number is None]
    assert [change.label for change in break_changes] == ["Spring Break (3/6 - 3/14)"]
    assert break_changes[0].old_date is None


def test_fall_to_summer_drops_breaks_the_target_term_does_not_have():
    new_course_data, preview = roll_over_course(
        _fall_2026_course(), target_term="Summer 2027", calendars=CALENDARS
    )

    assert _break_labels(new_course_data) == []
    assert any("Fall Break" in flag for flag in preview.general_flags)


def test_spring_to_fall_adds_every_break_within_the_course_span():
    spring_course = _course(
        term="Spring 2027",
        term_start=dt.date(2027, 1, 11),
        weeks_count=16,
        breaks=[("Spring Break", dt.date(2027, 3, 6), dt.date(2027, 3, 14))],
    )

    new_course_data, _ = roll_over_course(
        spring_course, target_term="Fall 2027", calendars=CALENDARS
    )

    assert _break_labels(new_course_data) == [
        "Fall Break (10/9 - 10/17)",
        "Thanksgiving Break (11/25 - 11/28)",
    ]


def test_breaks_after_the_course_ends_are_not_added():
    spring_course = _course(
        term="Spring 2027",
        term_start=dt.date(2027, 1, 11),
        weeks_count=10,  # Fall 2027 Week 10 ends Oct 31 — before Thanksgiving
        breaks=[("Spring Break", dt.date(2027, 3, 6), dt.date(2027, 3, 14))],
    )

    new_course_data, _ = roll_over_course(
        spring_course, target_term="Fall 2027", calendars=CALENDARS
    )

    assert _break_labels(new_course_data) == ["Fall Break (10/9 - 10/17)"]


def test_season_change_does_not_add_breaks_to_a_syllabus_that_listed_none():
    new_course_data, _ = roll_over_course(
        _fall_2026_course(breaks=[]), target_term="Spring 2027", calendars=CALENDARS
    )

    assert _break_labels(new_course_data) == []


def test_season_change_to_a_term_not_in_the_calendar_flags_the_stale_break():
    new_course_data, preview = roll_over_course(
        _fall_2026_course(),
        target_term="Spring 2031",
        calendars=CALENDARS,
        manual_week1_date=dt.date(2031, 1, 13),
    )

    assert len(_break_labels(new_course_data)) == 1  # kept; no calendar to replace it from
    assert any("Fall Break" in flag and "Spring 2031" in flag for flag in preview.general_flags)


def test_same_season_rollover_has_no_break_replacement_flag():
    _, preview = roll_over_course(_fall_2026_course(), target_term="Fall 2027", calendars=CALENDARS)

    assert not any("break" in flag.lower() for flag in preview.general_flags)


def test_fall_to_spring_renames_the_break_in_university_dates_and_keeps_order():
    university_dates = [
        UniversityDate(event="Classes begin", date=dt.date(2026, 8, 24)),
        UniversityDate(
            event="Fall Break", date_start=dt.date(2026, 10, 10), date_end=dt.date(2026, 10, 18)
        ),
        UniversityDate(event="Classes end", date=dt.date(2026, 12, 10)),
    ]

    new_course_data, _ = roll_over_course(
        _fall_2026_course(university_dates=university_dates),
        target_term="Spring 2027",
        calendars=CALENDARS,
    )

    events = new_course_data.university_dates
    assert [entry.event for entry in events] == ["Classes begin", "Spring Break", "Classes end"]
    assert (events[1].date_start, events[1].date_end) == (dt.date(2027, 3, 6), dt.date(2027, 3, 14))


def test_fall_to_spring_flags_university_dates_with_no_spring_equivalent():
    university_dates = [
        UniversityDate(event="Labor Day", date=dt.date(2026, 9, 7)),
        UniversityDate(
            event="Fall Break", date_start=dt.date(2026, 10, 10), date_end=dt.date(2026, 10, 18)
        ),
        UniversityDate(
            event="Thanksgiving Break",
            date_start=dt.date(2026, 11, 26),
            date_end=dt.date(2026, 11, 29),
        ),
    ]

    new_course_data, preview = roll_over_course(
        _fall_2026_course(university_dates=university_dates),
        target_term="Spring 2027",
        calendars=CALENDARS,
    )

    assert [entry.event for entry in new_course_data.university_dates] == [
        "Martin Luther King Jr. Day",
        "Spring Break",
        "Thanksgiving Break",
    ]
    flags = " ".join(preview.general_flags)
    assert "'Labor Day'" not in flags
    assert "Thanksgiving Break" in flags


# ---- Single-day holidays in the University Dates table -----------------------


def _calendars_with(term: str, start: str, end: str, no_class_dates: list[dict]) -> dict:
    return {"terms": [{"term": term, "start": start, "end": end, "no_class_dates": no_class_dates}]}


# Fall 2027 stays in, so Labor Day is a holiday the calendar data knows.
SPRING_2027_TWO_HOLIDAYS = {
    "terms": [
        *_calendars_with(
            "Spring 2027",
            "2027-01-11",
            "2027-04-27",
            [
                {"label": "Martin Luther King Jr. Day", "date": "2027-01-18"},
                {"label": "Presidents Day", "date": "2027-02-15"},
                {"label": "Spring Break", "date_start": "2027-03-06", "date_end": "2027-03-14"},
            ],
        )["terms"],
        *[term for term in CALENDARS["terms"] if term["term"] == "Fall 2027"],
    ]
}


def test_fall_to_spring_replaces_labor_day_with_the_spring_holiday():
    university_dates = [
        UniversityDate(event="Classes begin", date=dt.date(2026, 8, 24)),
        UniversityDate(event="Labor Day", date=dt.date(2026, 9, 7)),
        UniversityDate(event="Classes end", date=dt.date(2026, 12, 10)),
    ]

    new_course_data, preview = roll_over_course(
        _fall_2026_course(university_dates=university_dates),
        target_term="Spring 2027",
        calendars=CALENDARS,
    )

    holiday = new_course_data.university_dates[1]
    assert (holiday.event, holiday.date) == ("Martin Luther King Jr. Day", dt.date(2027, 1, 18))
    assert not any("Labor Day" in flag for flag in preview.general_flags)


def test_fall_to_spring_fills_holidays_in_order_and_flags_the_ones_left_over():
    university_dates = [UniversityDate(event="Labor Day", date=dt.date(2026, 9, 7))]

    new_course_data, preview = roll_over_course(
        _fall_2026_course(university_dates=university_dates),
        target_term="Spring 2027",
        calendars=SPRING_2027_TWO_HOLIDAYS,
    )

    assert [entry.event for entry in new_course_data.university_dates] == ["Martin Luther King Jr. Day"]
    flags = " ".join(preview.general_flags)
    assert "Presidents Day" in flags
    assert "2/15" in flags


def test_fall_to_spring_with_more_holidays_than_the_target_flags_the_extra_one():
    university_dates = [
        UniversityDate(event="Labor Day", date=dt.date(2026, 9, 7)),
        UniversityDate(event="Veterans Day", date=dt.date(2026, 11, 11)),
    ]
    calendars = {
        "terms": [
            *CALENDARS["terms"],
            {
                "term": "Fall 2030",
                "start": "2030-08-26",
                "end": "2030-12-12",
                "no_class_dates": [{"label": "Veterans Day", "date": "2030-11-11"}],
            },
        ]
    }

    new_course_data, preview = roll_over_course(
        _fall_2026_course(university_dates=university_dates),
        target_term="Spring 2027",
        calendars=calendars,
    )

    assert [entry.event for entry in new_course_data.university_dates] == [
        "Martin Luther King Jr. Day",
        "Veterans Day",
    ]
    assert any("'Veterans Day'" in flag for flag in preview.general_flags)


def test_season_change_never_renames_a_deadline_as_a_holiday():
    university_dates = [UniversityDate(event="Last day to drop", date=dt.date(2026, 9, 4))]

    new_course_data, preview = roll_over_course(
        _fall_2026_course(university_dates=university_dates),
        target_term="Spring 2027",
        calendars=CALENDARS,
    )

    assert new_course_data.university_dates[0].event == "Last day to drop"
    assert any("'Last day to drop'" in flag for flag in preview.general_flags)


def test_season_change_never_renames_a_deadline_that_names_a_holiday():
    university_dates = [
        UniversityDate(event="Labor Day", date=dt.date(2026, 9, 7)),
        UniversityDate(event="Last day to register before Labor Day", date=dt.date(2026, 9, 4)),
    ]

    new_course_data, preview = roll_over_course(
        _fall_2026_course(university_dates=university_dates),
        target_term="Spring 2027",
        calendars=SPRING_2027_TWO_HOLIDAYS,
    )

    assert [entry.event for entry in new_course_data.university_dates] == [
        "Martin Luther King Jr. Day",
        "Last day to register before Labor Day",
    ]
    assert any("'Last day to register before Labor Day'" in flag for flag in preview.general_flags)
    assert any("Presidents Day" in flag for flag in preview.general_flags)


def test_season_change_recognizes_a_holiday_followed_by_a_dashed_note():
    university_dates = [UniversityDate(event="Labor Day - no class", date=dt.date(2026, 9, 7))]

    new_course_data, _ = roll_over_course(
        _fall_2026_course(university_dates=university_dates),
        target_term="Spring 2027",
        calendars=CALENDARS,
    )

    assert new_course_data.university_dates[0].event == "Martin Luther King Jr. Day"


def test_season_change_without_holidays_in_the_table_adds_no_missing_holiday_flag():
    university_dates = [UniversityDate(event="Classes begin", date=dt.date(2026, 8, 24))]

    _, preview = roll_over_course(
        _fall_2026_course(university_dates=university_dates),
        target_term="Spring 2027",
        calendars=SPRING_2027_TWO_HOLIDAYS,
    )

    assert not any("Presidents Day" in flag for flag in preview.general_flags)


def test_same_season_holiday_takes_its_date_from_the_calendar():
    # 9/8 is a typo in the source; shifting by the term offset would keep it.
    university_dates = [UniversityDate(event="Labor Day", date=dt.date(2026, 9, 8))]

    new_course_data, _ = roll_over_course(
        _fall_2026_course(university_dates=university_dates),
        target_term="Fall 2027",
        calendars=CALENDARS,
    )

    assert new_course_data.university_dates[0].date == dt.date(2027, 9, 6)


def test_independence_day_is_a_holiday_not_the_end_of_term():
    university_dates = [
        UniversityDate(event="Memorial Day", date=dt.date(2026, 5, 25)),
        UniversityDate(event="Independence Day (observed)", date=dt.date(2026, 7, 3)),
    ]
    calendars = _calendars_with(
        "Summer 2027",
        "2027-05-17",
        "2027-08-04",
        [
            {"label": "Memorial Day", "date": "2027-05-31"},
            {"label": "Independence Day (observed)", "date": "2027-07-05"},
        ],
    )
    course = _course(
        term="Summer 2026",
        term_start=dt.date(2026, 5, 18),
        weeks_count=10,
        breaks=[],
        university_dates=university_dates,
    )

    new_course_data, _ = roll_over_course(course, target_term="Summer 2027", calendars=calendars)

    assert [entry.date for entry in new_course_data.university_dates] == [
        dt.date(2027, 5, 31),
        dt.date(2027, 7, 5),
    ]


def test_season_change_recognizes_a_holiday_written_with_extra_words():
    university_dates = [UniversityDate(event="Labor Day (no class)", date=dt.date(2026, 9, 7))]

    new_course_data, _ = roll_over_course(
        _fall_2026_course(university_dates=university_dates),
        target_term="Spring 2027",
        calendars=CALENDARS,
    )

    assert new_course_data.university_dates[0].event == "Martin Luther King Jr. Day"


def test_an_event_with_no_letters_matches_no_break_or_holiday():
    university_dates = [UniversityDate(event="—", date=dt.date(2026, 9, 7))]

    new_course_data, preview = roll_over_course(
        _fall_2026_course(university_dates=university_dates),
        target_term="Spring 2027",
        calendars=CALENDARS,
    )

    assert new_course_data.university_dates[0].event == "—"
    assert any("'—'" in flag for flag in preview.general_flags)
