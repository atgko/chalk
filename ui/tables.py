"""Pure row builders for the UI's tables — no Streamlit calls, so they're
unit-tested directly rather than through AppTest."""

from __future__ import annotations

import datetime as dt
from typing import Any

from chalk.models import CourseData
from chalk.rollover.preview import RolloverPreview, break_name


def _md(date: dt.date) -> str:
    return f"{date.strftime('%b')} {date.day} ({date.month}/{date.day})"


def week_rows(course_data: CourseData) -> list[dict[str, Any]]:
    rows = []
    for week in sorted(course_data.weeks, key=lambda w: w.date or w.date_start):
        if week.is_break:
            rows.append(
                {
                    "Week": "Break",
                    "Date": f"{_md(week.date_start)} – {_md(week.date_end)}",
                    "Topics": break_name(week.label),
                    "Assignments": "",
                    "Notes": "",
                }
            )
            continue
        rows.append(
            {
                "Week": str(week.week_number),
                "Date": _md(week.date),
                "Topics": "; ".join(week.topics),
                "Assignments": "; ".join(week.assignments),
                "Notes": week.notes or "",
            }
        )
    return rows


def assessment_rows(course_data: CourseData) -> list[dict[str, str]]:
    return [{"Assessment": a.name, "Weight": f"{a.weight * 100:g}%"} for a in course_data.assessments]


def university_date_rows(course_data: CourseData) -> list[dict[str, str]]:
    rows = []
    for entry in course_data.university_dates:
        when = _md(entry.date) if entry.date else f"{_md(entry.date_start)} – {_md(entry.date_end)}"
        rows.append({"Event": entry.event, "Date": when})
    return rows


def preview_rows(preview: RolloverPreview) -> list[dict[str, str]]:
    rows = []
    for change in preview.week_changes:
        is_break = change.week_number is None
        rows.append(
            {
                "Week": break_name(change.label) if is_break else f"Week {change.week_number}",
                "Current": _md(change.old_date) if change.old_date else "(new week)",
                "New": _md(change.new_date),
                "Check": "⚠ " + " / ".join(change.flags) if change.flags else "✓",
            }
        )
    return rows


def regular_week_count(course_data: CourseData) -> int:
    return sum(1 for week in course_data.weeks if not week.is_break)
