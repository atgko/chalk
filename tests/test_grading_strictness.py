"""Grading strictness (sponsor meeting, Oct 28): the grader picks how
strict the scores and feedback are; Standard leaves grading as it was."""

import pytest

from chalk import metrics
from chalk.grading import eval_log
from chalk.grading.strictness import (
    STANDARD,
    STRICTNESS_LEVELS,
    strictness_instructions,
    with_strictness,
)


def test_standard_adds_nothing_so_grading_is_unchanged():
    assert strictness_instructions(STANDARD) == ""
    assert with_strictness("Be consistent.", STANDARD) == "Be consistent."


@pytest.mark.parametrize("level", ["lenient", "strict"])
def test_lenient_and_strict_speak_to_both_the_scores_and_the_feedback(level):
    text = strictness_instructions(level)
    assert text.startswith(f"GRADING STRICTNESS: {level}.")
    assert "partial credit" in text and "feedback" in text
    assert "never deduct points for requirements the rubric doesn't state" in text.lower()


def test_strictness_comes_before_the_instructors_own_instructions():
    combined = with_strictness("Ignore spelling.", "strict")
    assert combined.startswith("GRADING STRICTNESS: strict.")
    assert combined.endswith("Ignore spelling.")
    assert with_strictness("", "lenient") == strictness_instructions("lenient")


def test_an_unknown_level_is_refused():
    assert STRICTNESS_LEVELS == ("lenient", "standard", "strict")
    with pytest.raises(ValueError, match="strictness"):
        strictness_instructions("harsh")


def test_grading_sends_the_strictness_and_logs_it(tmp_project, monkeypatch):
    seen = {}

    def fake_analyze(submission, rubric, instructions=""):
        seen["instructions"] = instructions
        return {"criteria": [{}]}

    monkeypatch.setattr(eval_log, "analyze_by_criterion", fake_analyze)

    eval_log.grade_and_log(tmp_project, "work", "rubric", "Ignore spelling.", strictness="strict")

    assert seen["instructions"].startswith("GRADING STRICTNESS: strict.")
    [event] = metrics.read_events_by_type(tmp_project.eval_log, "generation")
    assert event["strictness"] == "strict"
