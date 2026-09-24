import json

import pytest
from pydantic import ValidationError

from chalk.models import CourseData, UniversityDate, Week

# Matches PRD section 5.2's example course.json verbatim.
SAMPLE_COURSE_JSON = json.dumps(
    {
        "course": {
            "title": "IS 6640 Networking and Servers",
            "number": "IS 6640",
            "section": "090",
            "credits": 3,
            "term": "Fall 2026",
            "term_start": "2026-08-24",
            "term_end": "2026-10-26",
            "duration_weeks": 10,
            "meeting_pattern": "Online async",
            "instructor": "Dave Norwood",
            "source_format": "word",
            "source_file": "source/IS-6640-syllabus-fall-2026.docx",
            "extracted_at": "2026-09-17T10:00:00Z",
        },
        "learning_objectives": [
            "Understand the fundamentals of IT network infrastructure"
        ],
        "assessments": [
            {"name": "Video Quizzes", "weight": 0.05},
            {"name": "Labs", "weight": 0.25},
        ],
        "weeks": [
            {
                "week_number": 1,
                "date": "2026-08-24",
                "label": "Week 1 (8/24)",
                "is_break": False,
                "topics": ["Course Introduction", "Network+ Mod 1", "Network+ Mod 2"],
                "assignments": ["Network+ Lab A Due"],
                "notes": "Video Quizzes are Taken After Reading Each Chapter",
            },
            {
                "week_number": None,
                "date_start": "2026-10-10",
                "date_end": "2026-10-18",
                "label": "Fall Break",
                "is_break": True,
                "topics": [],
                "assignments": [],
            },
        ],
        "university_dates": [
            {"event": "Classes begin", "date": "2026-08-24"},
            {"event": "Fall Break", "date_start": "2026-10-10", "date_end": "2026-10-18"},
            {"event": "Classes end", "date": "2026-10-26"},
        ],
        "source_materials": [
            {"filename": "chapter-3-summary.pdf", "added_at": "2026-09-17T10:00:00Z"}
        ],
    }
)


def test_course_data_parses_the_prd_sample():
    course_data = CourseData.model_validate_json(SAMPLE_COURSE_JSON)

    assert course_data.course.title == "IS 6640 Networking and Servers"
    assert course_data.course.duration_weeks == 10
    assert course_data.weeks[0].week_number == 1
    assert course_data.weeks[0].is_break is False
    assert course_data.weeks[1].is_break is True
    assert course_data.weeks[1].week_number is None


def test_course_data_round_trips_through_json():
    course_data = CourseData.model_validate_json(SAMPLE_COURSE_JSON)
    dumped = course_data.model_dump_json()
    reparsed = CourseData.model_validate_json(dumped)
    assert reparsed == course_data


def test_duration_weeks_must_be_positive():
    bad_json = SAMPLE_COURSE_JSON.replace('"duration_weeks": 10', '"duration_weeks": 0')
    with pytest.raises(ValidationError):
        CourseData.model_validate_json(bad_json)


def test_non_break_week_requires_week_number_and_date():
    with pytest.raises(ValidationError):
        Week(label="Week 1 (8/24)", is_break=False, topics=[], assignments=[])


def test_break_week_requires_date_range():
    with pytest.raises(ValidationError):
        Week(label="Fall Break", is_break=True, topics=[], assignments=[])


def test_university_date_requires_single_date_or_range():
    with pytest.raises(ValidationError):
        UniversityDate(event="Some Event")


def test_university_date_accepts_single_date():
    ud = UniversityDate(event="Classes begin", date="2026-08-24")
    assert ud.date is not None


def test_university_date_accepts_date_range():
    ud = UniversityDate(event="Fall Break", date_start="2026-10-10", date_end="2026-10-18")
    assert ud.date_start is not None and ud.date_end is not None
