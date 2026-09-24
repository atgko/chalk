"""A canonical in-memory CourseData matching PRD section 5.2's example
JSON (IS 6640, 10 weeks, Fall 2026, with a Fall Break row), shared by
the Milestone 4+ tests that only need "a known-good course" rather than
one produced by a specific extractor fixture.
"""

import datetime as dt

from chalk.models import Assessment, CourseData, CourseInfo, UniversityDate, Week

TERM_START = dt.date(2026, 8, 24)


def build_sample_course_data(source_format: str = "word") -> CourseData:
    weeks = []
    for week_number in range(1, 11):
        week_date = TERM_START + dt.timedelta(days=7 * (week_number - 1))
        weeks.append(
            Week(
                week_number=week_number,
                date=week_date,
                label=f"Week {week_number} ({week_date.month}/{week_date.day})",
                topics=[f"Topic {week_number}A", f"Topic {week_number}B"],
                assignments=[f"Lab {week_number} Due"],
                notes="Video Quizzes are Taken After Reading Each Chapter" if week_number == 1 else None,
            )
        )
    weeks.insert(
        7,
        Week(
            date_start=dt.date(2026, 10, 10),
            date_end=dt.date(2026, 10, 18),
            label="Fall Break",
            is_break=True,
        ),
    )
    return CourseData(
        course=CourseInfo(
            title="IS 6640 Networking and Servers",
            number="IS 6640",
            section="090",
            credits=3,
            term="Fall 2026",
            term_start=TERM_START,
            term_end=dt.date(2026, 10, 26),
            duration_weeks=10,
            meeting_pattern="Online async",
            instructor="Dave Norwood",
            source_format=source_format,
            source_file="source/IS-6640-syllabus-fall-2026.docx",
            extracted_at=dt.datetime(2026, 9, 17, 10, 0, tzinfo=dt.timezone.utc),
        ),
        learning_objectives=[
            "Understand the fundamentals of IT network infrastructure",
            "Configure and secure Linux servers",
        ],
        assessments=[
            Assessment(name="Video Quizzes", weight=0.05),
            Assessment(name="Labs", weight=0.25),
        ],
        weeks=weeks,
        university_dates=[
            UniversityDate(event="Classes begin", date=TERM_START),
            UniversityDate(
                event="Fall Break", date_start=dt.date(2026, 10, 10), date_end=dt.date(2026, 10, 18)
            ),
        ],
    )
