"""Grading's entry in the eval log (BACKLOG.md, faculty meeting Oct 23):
the model, tokens, and cost of each grading, so the Metrics tab and
`toolkit.py report` show what grading costs.

Logged as a "generation" event with content_type "grading", like the AI
PDF reader, so it counts in every existing cost total. Metadata only:
never the submission, the rubric, the feedback, or the file name (a
Canvas SpeedGrader file name holds the student's name).
"""

from __future__ import annotations

from chalk import costs, metrics
from chalk.config import load_config
from chalk.generation.engine import current_env
from chalk.grading.strictness import STANDARD, with_strictness
from chalk.grading.workflow import analyze_by_criterion
from chalk.llm_client import UsageTally, track_usage
from chalk.project import ProjectPaths

GRADING_CONTENT_TYPE = "grading"


def grade_and_log(
    paths: ProjectPaths,
    submission: str,
    rubric: str,
    instructions: str = "",
    *,
    strictness: str = STANDARD,
) -> dict:
    """`analyze_by_criterion` at the chosen strictness
    (chalk.grading.strictness), plus one eval-log event for its AI calls.
    A grading that fails partway is still logged, since its calls were
    paid for; one that fails before any call isn't."""
    instructions = with_strictness(instructions, strictness)
    with track_usage() as usage:
        try:
            result = analyze_by_criterion(submission=submission, rubric=rubric, instructions=instructions)
        except Exception:
            if usage.calls:
                _log_grading(paths, usage, criterion_count=None, succeeded=False, strictness=strictness)
            raise
    _log_grading(paths, usage, criterion_count=len(result["criteria"]), succeeded=True, strictness=strictness)
    return result


def _log_grading(
    paths: ProjectPaths, usage: UsageTally, *, criterion_count: int | None, succeeded: bool, strictness: str
) -> None:
    env = current_env()
    metrics.append_event(
        paths.eval_log,
        "generation",
        {
            "content_type": GRADING_CONTENT_TYPE,
            "week_number": None,
            "output_file": None,
            "provider": env["LLM_PROVIDER"],
            "model": env["LLM_MODEL"] or "unknown model",
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": costs.cost_usd(
                costs.rate_for(load_config(paths.config_json), env), usage.input_tokens, usage.output_tokens
            ),
            "source_file_count": 0,
            "ai_calls": usage.calls,
            "criterion_count": criterion_count,
            "succeeded": succeeded,
            "strictness": strictness,
        },
    )
