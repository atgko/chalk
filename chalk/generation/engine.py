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
from chalk.generation.course_level import AI_COMPONENT_GUIDANCE, level_guidance
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
from chalk.progress import ProgressCallback, report, writing_progress
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
    # A "mixed" quiz's split. None for both leaves the split to the model.
    multiple_choice_count: int | None = None
    short_answer_count: int | None = None
    prompt_count: int = DEFAULT_PROMPT_COUNT
    assignment_name: str = ""
    assignment_description: str = ""
    assignment_mode: str = "create"
    assignment_goal: str = ""
    assignment_requirements: str = ""
    assignment_scenario: str = ""
    assignment_deliverables: str = ""
    assignment_format: str = ""
    assignment_evaluation: str = ""
    assignment_submission: str = ""
    total_points: int = DEFAULT_RUBRIC_POINTS
    slide_notes: str = ""
    source_files: tuple[str, ...] = ()
    # chalk/generation/course_level.py. None leaves the level to the model.
    course_level: str | None = None
    include_ai_component: bool = False  # assignments only


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
    suffix = "rubric" if spec.key == "rubric" else spec.key
    return folder / f"{slug}-{suffix}.md"


NO_SOURCES_MESSAGE = (
    "Choose at least one of your own source materials (a reading, handout, or notes) for Chalk "
    "to base the draft on. The syllabus alone isn't enough: drafts come from what you provide, "
    "not from the AI's general knowledge."
)


def require_source_files(course_data: CourseData, request: GenerationRequest) -> None:
    """Every draft rests on at least one instructor source file besides the
    syllabus, so the instructor, not the model, supplies the content
    (faculty meeting, Oct 23; BACKLOG.md). Raises GenerationError."""
    syllabus = Path(course_data.course.source_file).name
    if not [name for name in request.source_files if name != syllabus]:
        raise GenerationError(NO_SOURCES_MESSAGE)


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
    optional = _optional_guidance(spec, request)
    prompt = fill_template(template, variables | optional)
    # A template from before these variables existed: add the guidance at the end.
    unplaced = [text for name, text in optional.items() if text and f"{{{name}}}" not in template]
    if not unplaced:
        return prompt
    return "\n\n".join([prompt.rstrip(), *unplaced]) + "\n"


def _optional_guidance(spec: ContentSpec, request: GenerationRequest) -> dict[str, str]:
    """Course level and the assignment's AI-use component: optional
    template variables, empty when not asked for."""
    include_ai = spec.key == "assignment" and request.include_ai_component
    return {
        "course_level_guidance": level_guidance(request.course_level),
        "ai_component_guidance": AI_COMPONENT_GUIDANCE if include_ai else "",
    }


def _type_variables(spec: ContentSpec, course_data: CourseData, request: GenerationRequest) -> dict[str, str]:
    if not spec.per_week:
        if spec.key == "assignment":
            if not request.assignment_name.strip() or not request.assignment_goal.strip():
                raise GenerationError("An assignment needs a name and a learning goal.")
            if request.assignment_mode not in ("create", "enhance"):
                raise GenerationError("Assignment mode must be create or enhance.")
            if request.assignment_mode == "enhance" and not request.assignment_description.strip():
                raise GenerationError("Enhance mode needs the existing assignment text or an uploaded assignment.")

            if request.assignment_mode == "create":
                mode_instructions = (
                    "Create a new assignment using only the supplied learning goal, "
                    "requirements, course objectives, and relevant source material. "
                    "Do not discuss enhancing or revising an existing assignment. "
                    "Where details are missing, use [Faculty decision needed]."
                )
            else:
                mode_instructions = (
                    "Improve the existing assignment while preserving the instructor's "
                    "original purpose, requirements, and useful content. Improve clarity, "
                    "alignment, organization, student directions, and assessability without "
                    "silently changing the assignment. Do not discuss creating a new assignment. "
                    "Do not add new requirements unless supported by the instructor's information "
                    "or source materials. Where details are missing, use [Faculty decision needed]."
                )

            return {
                "assignment_detail_status": "\n".join(
                [
                    f"- {label}: PROVIDED BY INSTRUCTOR"
                    if value.strip()
                    else (
                    f"- {label}: NOT SPECIFIED IN THIS FIELD — "
                    "preserve any existing requirement found in the original assignment "
                    "or other instructor-provided fields; do not invent new requirements"
                )
                    for label, value in (
                        ("Requirements / constraints", request.assignment_requirements),
                        ("Scenario / context", request.assignment_scenario),
                        ("Required deliverables", request.assignment_deliverables),
                        ("Format / length", request.assignment_format),
                        ("Evaluation expectations", request.assignment_evaluation),
                        ("Submission details", request.assignment_submission),
                    )
                ]
            ),
            "assignment_mode": request.assignment_mode,
                "assignment_name": request.assignment_name.strip(),
                "assignment_goal": request.assignment_goal.strip(),
                "assignment_description": request.assignment_description.strip()
                or "(none - create a new assignment from the course context and goal)",
                "assignment_requirements": request.assignment_requirements.strip()
                or "(none specified)",
                "assignment_scenario": request.assignment_scenario.strip()
            or "(none specified)",
            "assignment_deliverables": request.assignment_deliverables.strip()
            or "(none specified)",
            "assignment_format": request.assignment_format.strip()
            or "(none specified)",
            "assignment_evaluation": request.assignment_evaluation.strip()
            or "(none specified)",
            "assignment_submission": request.assignment_submission.strip()
            or "(none specified)",
            "assignment_mode_instructions": mode_instructions,
            }

        if spec.key == "rubric":
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
        variables |= {"question_count": str(request.question_count), "format": _quiz_format_text(request)}
    elif spec.key == "discussion":
        _require_positive(request.prompt_count, "Prompt count")
        variables["prompt_count"] = str(request.prompt_count)
    elif spec.key == "slides":
        variables["slide_notes"] = request.slide_notes.strip() or "(none — use the week's topics)"
    return variables

def _quiz_format_text(request: GenerationRequest) -> str:
    """The `{format}` value. A mixed quiz's split goes inside it, so
    instructors' existing quiz templates carry it without a new variable."""
    mc, sa = request.multiple_choice_count, request.short_answer_count
    if request.quiz_format != "mixed" or (mc is None and sa is None):
        return request.quiz_format
    if mc is None or sa is None:
        raise GenerationError("Give both the multiple-choice and the short-answer count for a mixed quiz.")
    if mc < 1 or sa < 1:
        raise GenerationError(
            "A mixed quiz needs at least one multiple-choice and one short-answer question. "
            "Choose a single format otherwise."
        )
    if mc + sa != request.question_count:
        raise GenerationError(
            f"{mc} multiple choice and {sa} short answer make {mc + sa} questions, "
            f"not {request.question_count}."
        )
    return f"mixed (exactly {mc} multiple choice and {sa} short answer)"


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
    paths: ProjectPaths,
    course_data: CourseData,
    request: GenerationRequest,
    *,
    today: dt.date | None = None,
    on_progress: ProgressCallback | None = None,
) -> GeneratedDraft:
    """Run one LLM call and return the draft (not yet saved). Raises
    LLMProviderError / GenerationError / PromptTemplateError with
    plain-English messages. `on_progress` follows chalk/progress.py."""
    require_source_files(course_data, request)
    spec = spec_for(request.content_type)
    report(on_progress, None, "Preparing the prompt and source materials")
    prompt = build_prompt(paths, course_data, request)
    report(on_progress, None, "Waiting for the AI to start writing")
    result = complete(
        prompt,
        system=SYSTEM_PROMPT,
        max_tokens=spec.max_tokens,
        on_text=writing_progress(on_progress, expected_output_tokens(paths, spec)),
    )

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
    elif spec.key == "assignment":
        text = body
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


def expected_output_tokens(paths: ProjectPaths, spec: ContentSpec) -> int:
    """How long a reply of this type usually is in this project, for the
    progress bar. With no history yet, half the type's token limit: the
    limit is a ceiling, and replies rarely come near it."""
    typical = metrics.typical_output_tokens(paths.eval_log, spec.key)
    return typical if typical is not None else spec.max_tokens // 2


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
