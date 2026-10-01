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
import tempfile
from dataclasses import dataclass
from pathlib import Path

from chalk import costs, metrics
from chalk.calendar_data import find_term, load_calendars
from chalk.canvas_export import write_canvas_html
from chalk.config import load_config
from chalk.course_brief import write_course_brief
from chalk.errors import ChalkError, ProjectError, TermNotInCalendarError
from chalk.extractors import extract_course
from chalk.extractors.consistency import ConsistencyResult
from chalk.generation.engine import current_env
from chalk.llm_client import CompletionResult
from chalk.models import CourseData
from chalk.pdf_import import PdfReadMethod, converted_docx_name
from chalk.pdf_import.ai_reader import read_with_ai
from chalk.pdf_import.docx_writer import write_docx
from chalk.pdf_import.layout import read_pdf_blocks
from chalk.project import ProjectPaths, copy_into_source, load_course, save_course
from chalk.rollover.docx_rollover import write_rolled_over_docx
from chalk.rollover.markdown_rollover import write_rolled_over_markdown
from chalk.rollover.preview import RolloverPreview, roll_over_course

# The metrics/report label for an AI read of a PDF syllabus.
PDF_READING_CONTENT_TYPE = "pdf_syllabus_reading"
# Measured on an 11-page syllabus (~2,800 characters of text per page):
# the page's text goes in once and comes back out as JSON, plus the
# model's thinking. Only used for the "about $X per page" hint.
_AI_READING_INPUT_TOKENS_PER_PAGE = 800
_AI_READING_OUTPUT_TOKENS_PER_PAGE = 1200


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
    paths: ProjectPaths,
    syllabus_path,
    *,
    schedule_table_index: int | None = None,
    pdf_method: PdfReadMethod = "local",
    pdf_conversion: PdfConversion | None = None,
) -> tuple[CourseData, ConsistencyResult]:
    """Extract a syllabus and copy it into source/.

    A PDF is first converted to Word (convert_pdf_syllabus, read the way
    `pdf_method` says) and the Word file is what's extracted and stored.
    Pass `pdf_conversion` instead to reuse an earlier conversion — e.g.
    when the instructor picks a schedule table, so an AI read isn't paid
    for twice.

    Does NOT save course.json — the instructor reviews the result first
    (and decides what to do about a failed consistency check), then calls
    save_reviewed_course(). Failures are logged as `extraction_error`
    events and re-raised for the caller to show.
    """
    syllabus_path = Path(syllabus_path)
    if pdf_conversion is None and syllabus_path.suffix.lower() == ".pdf":
        pdf_conversion = convert_pdf_syllabus(paths, syllabus_path, method=pdf_method)
    pdf_details = {}
    if pdf_conversion is not None:
        syllabus_path = pdf_conversion.docx_path
        pdf_details = {"filename": pdf_conversion.pdf_name, "pdf_method": pdf_conversion.method}
    try:
        course_data, consistency = extract_course(
            syllabus_path, eval_log_path=paths.eval_log, schedule_table_index=schedule_table_index
        )
    except ChalkError as exc:
        metrics.append_event(
            paths.eval_log,
            "extraction_error",
            {"error_type": type(exc).__name__, "filename": syllabus_path.name, **pdf_details},
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
            **pdf_details,
        },
    )
    return course_data, consistency


@dataclass(frozen=True)
class PdfConversion:
    """A PDF syllabus read into a Word file (in a private temp folder until
    extraction copies it into source/). `cost_usd` is None for a local
    read, or for an AI read with a model that has no cost rate."""

    pdf_name: str
    docx_path: Path
    method: PdfReadMethod
    cost_usd: float | None = None


def convert_pdf_syllabus(paths: ProjectPaths, pdf_path, *, method: PdfReadMethod = "local") -> PdfConversion:
    """Read a PDF syllabus into "<name> (from PDF).docx". An AI read logs
    a `generation` event (tokens and cost, never content) so it counts
    toward the project's AI cost. Failures are logged as
    `extraction_error` events and re-raised."""
    pdf_path = Path(pdf_path)
    try:
        blocks = read_pdf_blocks(pdf_path)
        cost = None
        if method == "ai":
            blocks, completion = read_with_ai(blocks)
            cost = _log_ai_reading(paths, pdf_path, completion)
    except ChalkError as exc:
        metrics.append_event(
            paths.eval_log,
            "extraction_error",
            {"error_type": type(exc).__name__, "filename": pdf_path.name, "pdf_method": method},
        )
        raise
    docx_path = Path(tempfile.mkdtemp(prefix="chalk-pdf-")) / converted_docx_name(pdf_path)
    return PdfConversion(pdf_path.name, write_docx(blocks, docx_path), method, cost)


def estimate_ai_reading_cost_per_page(paths: ProjectPaths) -> float | None:
    """Rough cost of reading one PDF page with AI, shown before the
    instructor picks a reader. None when the model has no cost rate."""
    rate = costs.rate_for(load_config(paths.config_json), current_env())
    return costs.cost_usd(rate, _AI_READING_INPUT_TOKENS_PER_PAGE, _AI_READING_OUTPUT_TOKENS_PER_PAGE)


def _log_ai_reading(paths: ProjectPaths, pdf_path: Path, completion: CompletionResult) -> float | None:
    env = current_env()
    cost = costs.cost_usd(
        costs.rate_for(load_config(paths.config_json), env),
        completion["input_tokens"],
        completion["output_tokens"],
    )
    metrics.append_event(
        paths.eval_log,
        "generation",
        {
            "content_type": PDF_READING_CONTENT_TYPE,
            "week_number": None,
            "output_file": f"source/{converted_docx_name(pdf_path)}",
            "provider": env["LLM_PROVIDER"],
            "model": env["LLM_MODEL"] or "unknown model",
            "input_tokens": completion["input_tokens"],
            "output_tokens": completion["output_tokens"],
            "cost_usd": cost,
            "source_file_count": 0,
        },
    )
    return cost


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
