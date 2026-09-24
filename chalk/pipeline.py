"""End-to-end project workflows shared by the CLI and the Streamlit UI.

Each function here is one instructor-visible step — extract, save after
review, preview a rollover, confirm it, export — composed from the
lower-level feature modules and always operating on a ProjectPaths. The
UI and CLI call these and nothing lower, so both front ends log the same
metrics events and write the same files (PRD section 7: "the UI calls the
same functions the CLI does").
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from chalk import metrics
from chalk.calendar_data import find_term, load_calendars
from chalk.canvas_export import write_canvas_html
from chalk.course_brief import write_course_brief
from chalk.errors import ChalkError, ProjectError, TermNotInCalendarError
from chalk.extractors import extract_course
from chalk.extractors.consistency import ConsistencyResult
from chalk.models import CourseData
from chalk.project import ProjectPaths, copy_into_source, load_course, save_course
from chalk.rollover.docx_rollover import write_rolled_over_docx
from chalk.rollover.markdown_rollover import write_rolled_over_markdown
from chalk.rollover.preview import RolloverPreview, roll_over_course


@dataclass(frozen=True)
class RolloverPlan:
    """Everything the instructor reviews before confirming a rollover —
    nothing in here has been written to disk yet."""

    original: CourseData
    rolled_over: CourseData
    preview: RolloverPreview
    files_to_write: list[Path]


# ---- Extraction --------------------------------------------------------------


def extract_syllabus(
    paths: ProjectPaths, syllabus_path, *, schedule_table_index: int | None = None
) -> tuple[CourseData, ConsistencyResult]:
    """Extract a syllabus and copy it into source/.

    Does NOT save course.json — the instructor reviews the result first
    (and decides what to do about a failed consistency check), then calls
    save_reviewed_course(). Failures are logged as `extraction_error`
    events and re-raised for the caller to show.
    """
    syllabus_path = Path(syllabus_path)
    try:
        course_data, consistency = extract_course(
            syllabus_path, eval_log_path=paths.eval_log, schedule_table_index=schedule_table_index
        )
    except ChalkError as exc:
        metrics.append_event(
            paths.eval_log,
            "extraction_error",
            {"error_type": type(exc).__name__, "filename": syllabus_path.name},
        )
        raise

    stored = copy_into_source(paths, syllabus_path)
    previous = load_course(paths)
    course_data = course_data.model_copy(
        update={
            "course": course_data.course.model_copy(
                update={"source_file": stored.relative_to(paths.root).as_posix()}
            ),
            "source_materials": previous.source_materials if previous else [],
        }
    )

    metrics.append_event(
        paths.eval_log,
        "extraction",
        {
            "filename": syllabus_path.name,
            "source_format": course_data.course.source_format,
            "duration_weeks": course_data.course.duration_weeks,
            "week_rows": len(course_data.weeks),
        },
    )
    return course_data, consistency


def save_reviewed_course(paths: ProjectPaths, course_data: CourseData) -> list[Path]:
    """Save course.json after review and regenerate the course brief
    (F-04 runs automatically after every extraction)."""
    return [
        save_course(paths, course_data),
        write_course_brief(course_data, paths.course_brief, eval_log_path=paths.eval_log),
    ]


# ---- Rollover ------------------------------------------------------------------


def preview_rollover(
    paths: ProjectPaths,
    course_data: CourseData,
    target_term: str,
    *,
    target_duration_weeks: int | None = None,
    manual_week1_date: dt.date | None = None,
    llm_generate_topics: bool = True,
) -> RolloverPlan:
    """Compute a rollover without writing anything.

    Raises TermNotInCalendarError if `target_term` isn't in the project's
    calendars.json and no manual Week 1 date was given — the caller then
    asks for one and calls again.
    """
    calendars = load_calendars(paths.calendars_json)
    if find_term(calendars, target_term) is None and manual_week1_date is None:
        raise TermNotInCalendarError()

    rolled_over, preview = roll_over_course(
        course_data,
        target_term=target_term,
        calendars=calendars,
        target_duration_weeks=target_duration_weeks,
        manual_week1_date=manual_week1_date,
        llm_generate_topics=llm_generate_topics,
    )
    mismatch_flag = _duration_mismatch_flag(course_data, rolled_over.course.duration_weeks)
    if mismatch_flag:
        preview = dataclasses.replace(preview, general_flags=[mismatch_flag, *preview.general_flags])

    return RolloverPlan(
        original=course_data,
        rolled_over=rolled_over,
        preview=preview,
        files_to_write=[
            paths.syllabus_output(course_data.course.source_format),
            paths.canvas_html,
            paths.course_brief,
        ],
    )


def confirm_rollover(paths: ProjectPaths, plan: RolloverPlan) -> list[Path]:
    """Write every file in the plan (archiving previous versions), save
    the rolled-over course.json, and log a `rollover` event."""
    source_syllabus = _resolve_source_file(paths, plan.original)
    syllabus_output = plan.files_to_write[0]
    writer = (
        write_rolled_over_docx
        if plan.original.course.source_format == "word"
        else write_rolled_over_markdown
    )
    writer(source_syllabus, plan.rolled_over, syllabus_output, eval_log_path=paths.eval_log)

    written = [
        syllabus_output,
        write_canvas_html(plan.rolled_over, paths.canvas_html, eval_log_path=paths.eval_log),
        write_course_brief(plan.rolled_over, paths.course_brief, eval_log_path=paths.eval_log),
        save_course(paths, plan.rolled_over),
    ]

    preview = plan.preview
    metrics.append_event(
        paths.eval_log,
        "rollover",
        {
            "source_term": preview.source_term,
            "target_term": preview.target_term,
            "source_duration_weeks": preview.source_duration_weeks,
            "target_duration_weeks": preview.target_duration_weeks,
            "flag_count": len(preview.general_flags)
            + sum(len(change.flags) for change in preview.week_changes),
        },
    )
    return written


def _duration_mismatch_flag(course_data: CourseData, target_weeks: int) -> str | None:
    """PRD section 7.3's duration-mismatch check, surfaced as a preview
    flag rather than a hard stop: the extractor always sets duration_weeks
    to the schedule's week count, so a mismatch means the instructor
    changed it on purpose — the documented way to lengthen or shorten a
    course (section 6.2). See DECISIONS.md."""
    schedule_weeks = sum(1 for week in course_data.weeks if not week.is_break)
    if schedule_weeks == course_data.course.duration_weeks:
        return None
    return (
        f"The course has {schedule_weeks} weeks in the schedule but duration_weeks says "
        f"{course_data.course.duration_weeks}. The rolled-over schedule will have "
        f"{target_weeks} weeks — check the added or removed weeks before confirming."
    )


def _resolve_source_file(paths: ProjectPaths, course_data: CourseData) -> Path:
    source_file = Path(course_data.course.source_file)
    if not source_file.is_absolute():
        source_file = paths.root / source_file
    if not source_file.is_file():
        raise ProjectError(
            f"The original syllabus ({course_data.course.source_file}) is missing, so the "
            "rolled-over copy can't be written. Re-extract the syllabus and try again."
        )
    return source_file


# ---- Export ----------------------------------------------------------------------


def export_outputs(paths: ProjectPaths, course_data: CourseData) -> list[Path]:
    """Regenerate the zero-cost derived outputs (Canvas HTML, course
    brief) from the current course.json — available any time (F-03)."""
    return [
        write_canvas_html(course_data, paths.canvas_html, eval_log_path=paths.eval_log),
        write_course_brief(course_data, paths.course_brief, eval_log_path=paths.eval_log),
    ]
