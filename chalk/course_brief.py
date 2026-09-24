"""One-page course overview (F-04).

Built purely from course.json — no LLM call, zero cost (PRD section 6.4).
Regenerated automatically after every extraction and rollover by
chalk.project; this module only renders and writes it.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from chalk.archiving import archive_before_write
from chalk.models import CourseData, Week
from chalk.rollover.preview import break_name

_EMPTY_SECTION = "_None listed in the syllabus._"


def render_course_brief(course_data: CourseData) -> str:
    """Return the course brief as markdown."""
    sections = [
        _render_overview(course_data),
        _render_objectives(course_data.learning_objectives),
        _render_assessments(course_data),
        _render_schedule(course_data.weeks),
    ]
    return "\n\n".join(sections) + "\n"


def write_course_brief(course_data: CourseData, output_path, *, eval_log_path=None) -> Path:
    """Write the brief to `output_path` (normally outputs/course-brief.md),
    archiving any previous version first."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    archive_before_write(output_path, eval_log_path=eval_log_path)
    output_path.write_text(render_course_brief(course_data), encoding="utf-8")
    return output_path


def _render_overview(course_data: CourseData) -> str:
    course = course_data.course
    term_range = (
        f"{_short_date(course.term_start)} – {_short_date(course.term_end)}, {course.term_end.year}"
    )
    return "\n".join(
        [
            f"# {course.title}",
            "",
            f"- **Course:** {course.number} (Section {course.section})",
            f"- **Term:** {course.term} ({term_range})",
            f"- **Duration:** {course.duration_weeks} weeks",
            f"- **Credits:** {course.credits}",
            f"- **Meeting pattern:** {course.meeting_pattern}",
            f"- **Instructor:** {course.instructor}",
        ]
    )


def _render_objectives(objectives: list[str]) -> str:
    body = "\n".join(f"{i}. {text}" for i, text in enumerate(objectives, start=1))
    return "## Learning Objectives\n\n" + (body or _EMPTY_SECTION)


def _render_assessments(course_data: CourseData) -> str:
    if not course_data.assessments:
        return "## Assessment Weights\n\n" + _EMPTY_SECTION
    rows = [
        f"| {_cell(a.name)} | {_format_percent(a.weight)} |" for a in course_data.assessments
    ]
    return "\n".join(["## Assessment Weights", "", "| Assessment | Weight |", "| --- | --- |", *rows])


def _render_schedule(weeks: list[Week]) -> str:
    rows = [_render_schedule_row(week) for week in sorted(weeks, key=_week_sort_key)]
    return "\n".join(["## Schedule", "", "| Week | Date | Topic |", "| --- | --- | --- |", *rows])


def _render_schedule_row(week: Week) -> str:
    if week.is_break:
        dates = f"{_short_date(week.date_start)} – {_short_date(week.date_end)}"
        return f"| — | {dates} | {_cell(break_name(week.label))} |"
    topic = "; ".join(week.topics) or "—"
    return f"| {week.week_number} | {_short_date(week.date)} | {_cell(topic)} |"


def _cell(text: str) -> str:
    """Escape pipes so course content can't split a markdown table cell."""
    return text.replace("|", "\\|")


def _format_percent(weight: float) -> str:
    return f"{weight * 100:g}%"


def _short_date(date: dt.date) -> str:
    return f"{date.strftime('%b')} {date.day}"


def _week_sort_key(week: Week) -> dt.date:
    return week.date if week.date is not None else week.date_start
