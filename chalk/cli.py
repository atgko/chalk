"""Command-line interface (F-06) — `python toolkit.py <command>`.

Lives inside the package (toolkit.py is a two-line shim) so it's covered
by the same test run as everything else. Every command is a thin layer
over chalk.project / chalk.pipeline: parse arguments, call one workflow
function, print plain-English results. ChalkError messages are printed
as-is and never as tracebacks (PRD section 7.3).

`input_fn` and the output streams are injectable so integration tests
can drive the interactive confirmations without a terminal.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from dotenv import load_dotenv

from chalk import branding
from chalk.config import describe_provider
from chalk.costs import format_cost
from chalk.errors import ChalkError, TermNotInCalendarError
from chalk.extractors import log_consistency_override
from chalk.generation.engine import (
    GenerationRequest,
    current_env,
    estimate_cost,
    generate,
    overwrite_warning,
    save_draft,
    spec_for,
)
from chalk.generation.source_context import read_source_text
from chalk.generation.specs import (
    DEFAULT_PROMPT_COUNT,
    DEFAULT_QUESTION_COUNT,
    DEFAULT_RUBRIC_POINTS,
    QUIZ_FORMATS,
    SPECS,
)
from chalk.models import CourseData
from chalk.pipeline import (
    RolloverPlan,
    confirm_rollover,
    export_outputs,
    extract_syllabus,
    preview_rollover,
    save_reviewed_course,
)
from chalk.project import (
    ProjectPaths,
    ProjectStatus,
    add_source,
    init_project,
    open_project,
    project_status,
    require_course,
)

_RULE = "─" * 64

InputFn = Callable[[str], str]


class _Console:
    def __init__(self, out: TextIO, err: TextIO, input_fn: InputFn):
        self.out = out
        self.err = err
        self.input_fn = input_fn

    def say(self, text: str = "") -> None:
        print(text, file=self.out)

    def error(self, text: str) -> None:
        print(f"Error: {text}", file=self.err)

    def confirm(self, question: str) -> bool:
        return self.input_fn(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def main(
    argv: list[str] | None = None,
    *,
    input_fn: InputFn = input,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    console = _Console(out or sys.stdout, err or sys.stderr, input_fn)
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args, console)
    except ChalkError as exc:
        console.error(exc.user_message)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toolkit.py",
        description=f"{branding.PROJECT_NAME} — syllabus maintenance and course material toolkit.",
    )
    project_arg = argparse.ArgumentParser(add_help=False)
    project_arg.add_argument(
        "--project", type=Path, default=Path.cwd(), help="Course project folder (default: current folder)."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create a new course project folder.")
    init.add_argument("--name", required=True, help='Project name, e.g. "IS-6640-Fall-2027".')
    init.add_argument("--dir", type=Path, default=Path.cwd(), help="Where to create it (default: current folder).")
    init.set_defaults(handler=_cmd_init)

    add = commands.add_parser("add", parents=[project_arg], help="Index a source-material file.")
    add.add_argument("file", type=Path)
    add.set_defaults(handler=_cmd_add)

    extract = commands.add_parser("extract", parents=[project_arg], help="Extract course.json from a syllabus.")
    extract.add_argument("file", type=Path, help="The .docx or .md syllabus.")
    extract.add_argument(
        "--continue-anyway",
        action="store_true",
        help="Save even if the term/Week-1 consistency check fails (the override is logged).",
    )
    extract.set_defaults(handler=_cmd_extract)

    rollover = commands.add_parser("rollover", parents=[project_arg], help="Roll the course to a new term.")
    rollover.add_argument("--term", required=True, help='Target term, e.g. "Fall 2027".')
    rollover.add_argument("--weeks", type=int, help="New course length in weeks (default: unchanged).")
    rollover.add_argument("--week1-date", type=_parse_date, help="First day of classes (YYYY-MM-DD), for terms not in the calendar.")
    rollover.add_argument("--no-llm", action="store_true", help="Don't ask the LLM to draft topics for added weeks.")
    rollover.add_argument("--yes", action="store_true", help="Write the files without asking for confirmation.")
    rollover.set_defaults(handler=_cmd_rollover)

    export = commands.add_parser("export", parents=[project_arg], help="Regenerate Canvas HTML and the course brief.")
    export.set_defaults(handler=_cmd_export)

    generate = commands.add_parser(
        "generate", parents=[project_arg], help="Generate an AI draft (quiz, discussion, rubric, summary, slides)."
    )
    generate.add_argument("type", choices=list(SPECS))
    generate.add_argument("--week", type=int, help="Week number (all types except rubric).")
    generate.add_argument("--count", type=int, help="Quiz questions (default 5) or discussion prompts (default 3).")
    generate.add_argument("--format", choices=QUIZ_FORMATS, default="mixed", help="Quiz question format.")
    generate.add_argument("--assignment", help="Rubric: the assignment's name.")
    generate.add_argument("--description", help="Rubric: the assignment description, as text.")
    generate.add_argument("--description-file", type=Path, help="Rubric: read the description from a file.")
    generate.add_argument("--points", type=int, default=DEFAULT_RUBRIC_POINTS, help="Rubric: total points.")
    generate.add_argument("--notes", help="Slides: bullet points or a reading excerpt.")
    generate.add_argument("--source", action="append", help="A file in source/ to ground the draft in (repeatable).")
    generate.add_argument("--yes", action="store_true", help="Overwrite an existing draft without asking.")
    generate.set_defaults(handler=_cmd_generate)

    status = commands.add_parser("status", parents=[project_arg], help="Show a project summary.")
    status.set_defaults(handler=_cmd_status)

    return parser


# ---- Commands ----------------------------------------------------------------


def _cmd_init(args, console: _Console) -> int:
    paths = init_project(args.dir, args.name)
    console.say(f"Created course project at {paths.root}")
    console.say("Next: copy your provider settings into .env (see .env.example), then run")
    console.say(f'  python toolkit.py extract path/to/syllabus.docx --project "{paths.root}"')
    return 0


def _cmd_add(args, console: _Console) -> int:
    paths = open_project(args.project)
    destination = add_source(paths, args.file)
    console.say(f"Added {destination.name} to source/.")
    return 0


def _cmd_extract(args, console: _Console) -> int:
    paths = open_project(args.project)
    course_data, consistency = extract_syllabus(paths, args.file)
    console.say(_format_course_summary(course_data))

    if not consistency.passed:
        console.say()
        console.say("⚠ Term and schedule don't match")
        console.say(consistency.detail)
        if not (args.continue_anyway or console.confirm("Continue anyway?")):
            console.say("Cancelled — course.json was not saved.")
            return 1
        log_consistency_override(paths.eval_log, consistency)

    for path in save_reviewed_course(paths, course_data):
        console.say(f"Wrote {_relative(path, paths)}")
    console.say("Review course.json (especially duration_weeks) before rolling over.")
    return 0


def _cmd_rollover(args, console: _Console) -> int:
    paths = open_project(args.project)
    if paths.env.exists():
        load_dotenv(paths.env, override=False)
    course_data = require_course(paths)
    plan = _preview_with_week1_fallback(paths, course_data, args, console)
    if plan is None:
        return 1

    console.say(format_preview(plan, paths))
    if not (args.yes or console.confirm("Confirm and write these files?")):
        console.say("Cancelled — nothing was written.")
        return 1

    for path in confirm_rollover(paths, plan):
        console.say(f"Wrote {_relative(path, paths)}")
    return 0


def _cmd_export(args, console: _Console) -> int:
    paths = open_project(args.project)
    for path in export_outputs(paths, require_course(paths)):
        console.say(f"Wrote {_relative(path, paths)}")
    return 0


def _cmd_generate(args, console: _Console) -> int:
    paths = open_project(args.project)
    if paths.env.exists():
        load_dotenv(paths.env, override=False)
    if describe_provider(current_env()) == "Not configured":
        raise ChalkError(
            "No LLM provider is configured. Copy .env.example to this project's .env and fill it in, "
            "or set one up in the app's Settings tab."
        )
    course_data = require_course(paths)
    request = _generation_request(args)
    if spec_for(request.content_type).per_week and request.week_number is None:
        raise ChalkError("Say which week to generate for, e.g. --week 3.")

    warning = overwrite_warning(paths, request)
    if warning and not (args.yes or console.confirm(warning)):
        console.say("Cancelled — nothing was generated.")
        return 1

    estimate = estimate_cost(paths, course_data, request)
    console.say(f"Estimated cost: {format_cost(estimate, prefix='up to ~')}. Generating…")
    draft = generate(paths, course_data, request)
    path = save_draft(paths, draft)
    console.say(f"Wrote {_relative(path, paths)}")
    console.say(
        f"Tokens: {draft.input_tokens:,} in / {draft.output_tokens:,} out · Cost: {format_cost(draft.cost_usd)}"
    )
    console.say("This is an AI-generated draft — review and edit it before use.")
    return 0


def _generation_request(args) -> GenerationRequest:
    description = args.description or ""
    if args.description_file is not None:
        if not args.description_file.is_file():
            raise ChalkError(f"Couldn't find '{args.description_file}'. Check the path and try again.")
        description = read_source_text(args.description_file)
    return GenerationRequest(
        content_type=args.type,
        week_number=args.week,
        question_count=args.count or DEFAULT_QUESTION_COUNT,
        quiz_format=args.format,
        prompt_count=args.count or DEFAULT_PROMPT_COUNT,
        assignment_name=args.assignment or "",
        assignment_description=description,
        total_points=args.points,
        slide_notes=args.notes or "",
        source_files=tuple(args.source or ()),
    )





def _cmd_status(args, console: _Console) -> int:
    paths = open_project(args.project)
    console.say(format_status(project_status(paths), paths))
    return 0


# ---- Rollover helpers -----------------------------------------------------------


def _preview_with_week1_fallback(
    paths: ProjectPaths, course_data: CourseData, args, console: _Console
) -> RolloverPlan | None:
    kwargs = {
        "target_duration_weeks": args.weeks,
        "llm_generate_topics": not args.no_llm,
    }
    try:
        return preview_rollover(paths, course_data, args.term, manual_week1_date=args.week1_date, **kwargs)
    except TermNotInCalendarError as exc:
        if args.yes:
            raise
        console.say(exc.user_message)
        answer = console.input_fn("First day of classes (YYYY-MM-DD): ").strip()
        try:
            week1_date = dt.date.fromisoformat(answer)
        except ValueError:
            console.error(f"'{answer}' isn't a date in YYYY-MM-DD form.")
            return None
        return preview_rollover(paths, course_data, args.term, manual_week1_date=week1_date, **kwargs)


def format_preview(plan: RolloverPlan, paths: ProjectPaths) -> str:
    """Render a RolloverPlan in the PRD section 6.2 preview layout."""
    preview = plan.preview
    number = plan.original.course.number
    lines = [
        f"ROLLOVER PREVIEW: {number} ({preview.source_duration_weeks} weeks) → {preview.target_term}",
        _RULE,
        _preview_row("Term label:", f'"{preview.source_term}"', f'"{preview.target_term}"', []),
        _preview_row(
            "Duration:",
            f"{preview.source_duration_weeks} weeks",
            f"{preview.target_duration_weeks} weeks",
            preview.general_flags,
        ),
    ]
    for change in preview.week_changes:
        name = f"Week {change.week_number}:" if change.week_number is not None else "Break:"
        old = _preview_date(change.old_date) if change.old_date else "(new week)"
        lines.append(_preview_row(name, old, _preview_date(change.new_date), change.flags))
        if change.week_number is None:
            lines.append(f"{'':14}{change.label}")
    lines += [_RULE, "Files to be written:"]
    lines += [f"  {_relative(path, paths)}" for path in plan.files_to_write]
    return "\n".join(lines)


def _preview_row(name: str, old: str, new: str, flags: list[str]) -> str:
    row = f"{name:<14}{old:<16}→ {new:<16}{'⚠' if flags else '✓'}"
    return "\n".join([row, *(f"{'':14}⚠ {flag}" for flag in flags)])


def _preview_date(date: dt.date) -> str:
    return f"{date.strftime('%b')} {date.day} ({date.month}/{date.day})"


# ---- Formatting -------------------------------------------------------------------


def _format_course_summary(course_data: CourseData) -> str:
    course = course_data.course
    breaks = sum(1 for week in course_data.weeks if week.is_break)
    return "\n".join(
        [
            f"Extracted: {course.title} — {course.term}",
            (
                f"  {course.duration_weeks} weeks ({breaks} break rows), "
                f"{len(course_data.learning_objectives)} learning objectives, "
                f"{len(course_data.assessments)} assessments, "
                f"{len(course_data.university_dates)} university dates"
            ),
        ]
    )


def format_status(status: ProjectStatus, paths: ProjectPaths) -> str:
    if status.course is None:
        course_line = "No course.json yet — run `extract` on your syllabus."
    else:
        course = status.course.course
        course_line = f"{course.title} — {course.term}, {course.duration_weeks} weeks"
    outputs = ", ".join(f"{name}: {count}" for name, count in status.output_counts.items() if count)
    return "\n".join(
        [
            f"Project:       {status.name} ({paths.root})",
            f"Course:        {course_line}",
            f"Source files:  {len(status.source_files)}"
            + (f" ({', '.join(status.source_files)})" if status.source_files else ""),
            f"Outputs:       {outputs or 'none yet'}",
            f"Rollovers:     {status.rollover_count}",
            f"Consistency-check catches: {status.consistency_failures}",
            f"Extraction errors:         {status.extraction_error_count}",
            f"Total LLM cost to date:    ${status.total_cost_usd:.4f}",
        ]
    )


def _relative(path: Path, paths: ProjectPaths) -> str:
    try:
        return path.relative_to(paths.root).as_posix()
    except ValueError:  # pragma: no cover - every workflow writes inside the project
        return str(path)


def _parse_date(text: str) -> dt.date:
    try:
        return dt.date.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"'{text}' isn't a date in YYYY-MM-DD form.") from exc
