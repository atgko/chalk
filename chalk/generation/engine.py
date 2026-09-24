"""Content generation (F-05): request -> prompt -> LLM -> reviewed draft
-> saved file.

`generate()` makes the call, logs a `generation` event (tokens, cost —
never content), and returns a GeneratedDraft *without writing it*: the UI
shows the draft for review before the instructor saves (PRD section 7.2).
`save_draft()` then archives any previous version and writes the file.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass
from pathlib import Path

from chalk import costs, metrics
from chalk.archiving import archive_before_write
from chalk.config import load_config
from chalk.errors import GenerationError
from chalk.generation.prompts import fill_template, load_template
from chalk.generation.slides import normalize_slides
from chalk.generation.source_context import build_source_context
from chalk.generation.specs import (
    DEFAULT_PROMPT_COUNT,
    DEFAULT_QUESTION_COUNT,
    DEFAULT_RUBRIC_POINTS,
    QUIZ_FORMATS,
    SPECS,
    ContentSpec,
)
from chalk.llm_client import complete
from chalk.models import CourseData, Week
from chalk.project import ProjectPaths

SYSTEM_PROMPT = (
    "You draft course materials for a university instructor, who will review and edit "
    "everything before use. Follow the requested format exactly. Never grade, score, or "
    "evaluate student work."
)
_ENV_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")
_WRAPPING_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n(.*)\n```$", re.DOTALL)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class GenerationRequest:
    content_type: str
    week_number: int | None = None
    question_count: int = DEFAULT_QUESTION_COUNT
    quiz_format: str = "mixed"
    prompt_count: int = DEFAULT_PROMPT_COUNT
    assignment_name: str = ""
    assignment_description: str = ""
    total_points: int = DEFAULT_RUBRIC_POINTS
    slide_notes: str = ""
    source_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedDraft:
    request: GenerationRequest
    text: str
    output_path: Path
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


# ---- Request -> prompt ---------------------------------------------------------------


def spec_for(content_type: str) -> ContentSpec:
    try:
        return SPECS[content_type]
    except KeyError:
        raise GenerationError(
            f"Unknown content type '{content_type}'. Choose one of: {', '.join(SPECS)}."
        ) from None


def output_path_for(paths: ProjectPaths, request: GenerationRequest) -> Path:
    spec = spec_for(request.content_type)
    folder = paths.outputs_dir / spec.output_subdir
    if spec.per_week:
        return folder / f"week-{request.week_number}-{spec.key}.md"
    slug = _SLUG_RE.sub("-", request.assignment_name.lower()).strip("-") or "assignment"
    return folder / f"{slug}-rubric.md"


def build_prompt(paths: ProjectPaths, course_data: CourseData, request: GenerationRequest) -> str:
    spec = spec_for(request.content_type)
    template = load_template(paths.prompts_dir, spec)
    variables = {
        "course_title": course_data.course.title,
        "learning_objectives": "\n".join(f"- {o}" for o in course_data.learning_objectives)
        or "(none listed in the syllabus)",
        "source_material_context": build_source_context(paths, list(request.source_files)),
        **_type_variables(spec, course_data, request),
    }
    return fill_template(template, variables)


def _type_variables(spec: ContentSpec, course_data: CourseData, request: GenerationRequest) -> dict[str, str]:
    if not spec.per_week:
        if not request.assignment_name.strip() or not request.assignment_description.strip():
            raise GenerationError("A rubric needs an assignment name and a description of the assignment.")
        _require_positive(request.total_points, "Total points")
        return {
            "assignment_name": request.assignment_name.strip(),
            "assignment_description": request.assignment_description.strip(),
            "total_points": str(request.total_points),
        }

    week = _find_week(course_data, request.week_number)
    variables = {
        "week_number": str(week.week_number),
        "topics": "; ".join(week.topics) or "(no topics listed for this week)",
    }
    if spec.key == "quiz":
        _require_positive(request.question_count, "Question count")
        if request.quiz_format not in QUIZ_FORMATS:
            raise GenerationError(f"Quiz format must be one of: {', '.join(QUIZ_FORMATS)}.")
        variables |= {"question_count": str(request.question_count), "format": request.quiz_format}
    elif spec.key == "discussion":
        _require_positive(request.prompt_count, "Prompt count")
        variables["prompt_count"] = str(request.prompt_count)
    elif spec.key == "slides":
        variables["slide_notes"] = request.slide_notes.strip() or "(none — use the week's topics)"
    return variables


def _find_week(course_data: CourseData, week_number: int | None) -> Week:
    for week in course_data.weeks:
        if not week.is_break and week.week_number == week_number:
            return week
    raise GenerationError(
        f"Week {week_number} isn't in this course's schedule "
        f"(weeks 1–{course_data.course.duration_weeks})."
    )


def _require_positive(value: int, name: str) -> None:
    if value < 1:
        raise GenerationError(f"{name} must be at least 1.")


# ---- Cost ---------------------------------------------------------------------------


def current_env() -> dict[str, str]:
    return {key: os.environ.get(key, "") for key in _ENV_KEYS}


def estimate_cost(paths: ProjectPaths, course_data: CourseData, request: GenerationRequest) -> float | None:
    """"Up to ~$X" before generation. None when the model has no rate."""
    prompt = build_prompt(paths, course_data, request)
    rate = costs.rate_for(load_config(paths.config_json), current_env())
    return costs.estimate_max_cost(rate, SYSTEM_PROMPT + prompt, spec_for(request.content_type).max_tokens)


# ---- Generate / save ----------------------------------------------------------------


def generate(
    paths: ProjectPaths, course_data: CourseData, request: GenerationRequest, *, today: dt.date | None = None
) -> GeneratedDraft:
    """Run one LLM call and return the draft (not yet saved). Raises
    LLMProviderError / GenerationError / PromptTemplateError with
    plain-English messages."""
    spec = spec_for(request.content_type)
    prompt = build_prompt(paths, course_data, request)
    result = complete(prompt, system=SYSTEM_PROMPT, max_tokens=spec.max_tokens)

    env = current_env()
    model = env["LLM_MODEL"] or "unknown model"
    cost = costs.cost_usd(
        costs.rate_for(load_config(paths.config_json), env), result["input_tokens"], result["output_tokens"]
    )
    output_path = output_path_for(paths, request)
    metrics.append_event(
        paths.eval_log,
        "generation",
        {
            "content_type": spec.key,
            "week_number": request.week_number if spec.per_week else None,
            "output_file": output_path.relative_to(paths.root).as_posix(),
            "provider": env["LLM_PROVIDER"],
            "model": model,
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "cost_usd": cost,
            "source_file_count": len(request.source_files),
        },
    )

    banner = f"Generated {(today or dt.date.today()).isoformat()} using {model}."
    body = _strip_wrapping_fence(result["text"].strip())
    if spec.key == "slides":
        week = _find_week(course_data, request.week_number)
        text = normalize_slides(
            body,
            default_title=f"Week {week.week_number}: {'; '.join(week.topics) or course_data.course.title}",
            author=course_data.course.instructor,
            banner=f"AI-generated draft — review and edit before use. {banner}",
        )
    else:
        text = f"> **AI-generated draft** — review and edit before use. {banner}\n\n{body}\n"

    return GeneratedDraft(
        request=request,
        text=text,
        output_path=output_path,
        model=model,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        cost_usd=cost,
    )


def save_draft(paths: ProjectPaths, draft: GeneratedDraft) -> Path:
    """Write a reviewed draft, archiving any previous version (F-06)."""
    draft.output_path.parent.mkdir(parents=True, exist_ok=True)
    archive_before_write(draft.output_path, eval_log_path=paths.eval_log)
    draft.output_path.write_text(draft.text, encoding="utf-8")
    return draft.output_path


def overwrite_warning(paths: ProjectPaths, request: GenerationRequest) -> str | None:
    """PRD section 7.3's confirmation text, if this request's output
    file already exists."""
    if not output_path_for(paths, request).exists():
        return None
    spec = spec_for(request.content_type)
    subject = f"Week {request.week_number}" if spec.per_week else f"“{request.assignment_name.strip()}”"
    return (
        f"A {spec.label.lower()} already exists for {subject}. Generating a new one will archive "
        "the old version. Continue?"
    )


def _strip_wrapping_fence(text: str) -> str:
    match = _WRAPPING_FENCE_RE.match(text)
    return match.group(1).strip() if match else text
