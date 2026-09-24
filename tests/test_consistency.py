import datetime as dt

from chalk.extractors.consistency import check_term_consistency
from chalk.models import CourseData, CourseInfo, Week


def _course_data(term: str, week1_date: dt.date) -> CourseData:
    return CourseData(
        course=CourseInfo(
            title="IS 6640 Networking and Servers",
            number="IS 6640",
            section="090",
            credits=3,
            term=term,
            term_start=week1_date,
            term_end=week1_date,
            duration_weeks=1,
            meeting_pattern="Online async",
            instructor="Dave Norwood",
            source_format="word",
            source_file="source/syllabus.docx",
            extracted_at=dt.datetime(2026, 9, 17, tzinfo=dt.timezone.utc),
        ),
        weeks=[
            Week(
                week_number=1,
                date=week1_date,
                label=f"Week 1 ({week1_date.month}/{week1_date.day})",
                is_break=False,
                topics=["Course Introduction"],
            )
        ],
    )


def test_reproduces_the_named_sponsor_bug_spring_label_with_august_week_one():
    # PRD section 3: "the sponsor's own Spring 2026 syllabus carries Fall
    # 2025 schedule dates" — the term label was updated but the schedule
    # table was not. This is the flagship named test case.
    course_data = _course_data(term="Spring 2026", week1_date=dt.date(2026, 8, 18))

    result = check_term_consistency(course_data)

    assert result.passed is False
    assert 'Term label says: "Spring 2026"' in result.detail
    assert "August 18" in result.detail
    assert "fall semester start" in result.detail


def test_matching_fall_term_and_august_week_one_passes():
    course_data = _course_data(term="Fall 2026", week1_date=dt.date(2026, 8, 24))

    result = check_term_consistency(course_data)

    assert result.passed is True
    assert result.detail is None


def test_matching_spring_term_and_january_week_one_passes():
    course_data = _course_data(term="Spring 2027", week1_date=dt.date(2027, 1, 11))

    assert check_term_consistency(course_data).passed is True


def test_matching_summer_term_and_may_week_one_passes():
    course_data = _course_data(term="Summer 2027", week1_date=dt.date(2027, 5, 17))

    assert check_term_consistency(course_data).passed is True


def test_term_with_no_recognizable_season_word_cannot_be_evaluated_and_passes():
    course_data = _course_data(term="2026-2027 Academic Year", week1_date=dt.date(2026, 8, 24))

    assert check_term_consistency(course_data).passed is True


def test_no_week_one_present_cannot_be_evaluated_and_passes():
    course_data = _course_data(term="Fall 2026", week1_date=dt.date(2026, 8, 24))
    week_two = Week(
        week_number=2, date=dt.date(2026, 8, 31), label="Week 2 (8/31)", is_break=False
    )
    course_data = course_data.model_copy(update={"weeks": [week_two]})

    result = check_term_consistency(course_data)

    assert result.passed is True
    assert result.week1_date is None


def test_mismatch_message_falls_back_to_a_best_guess_season_for_a_mid_semester_month():
    # March isn't in any season's *start* window (fall={8,9}, spring={1,2},
    # summer={5,6}) -- exercises the message's fallback guess, distinct
    # from the pass/fail verdict itself.
    course_data = _course_data(term="Fall 2026", week1_date=dt.date(2026, 3, 15))

    result = check_term_consistency(course_data)

    assert result.passed is False
    assert "spring semester start" in result.detail


def test_mismatch_message_fallback_guesses_fall_for_a_late_autumn_month():
    course_data = _course_data(term="Spring 2026", week1_date=dt.date(2026, 11, 10))

    result = check_term_consistency(course_data)

    assert result.passed is False
    assert "fall semester start" in result.detail


def test_mismatch_message_fallback_guesses_summer_as_the_last_resort():
    course_data = _course_data(term="Fall 2026", week1_date=dt.date(2026, 7, 4))

    result = check_term_consistency(course_data)

    assert result.passed is False
    assert "summer semester start" in result.detail
