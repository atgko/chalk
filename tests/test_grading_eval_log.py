"""Tests for chalk.grading.eval_log: each grading's AI calls, tokens, and
cost go in the eval log, never the submission, rubric, or feedback. The
provider SDK is faked (as in test_llm_client.py), so the real
llm_client.complete counts the calls."""

import json

import pytest

from chalk import metrics
from chalk.errors import LLMProviderError
from chalk.grading.eval_log import GRADING_CONTENT_TYPE, grade_and_log
from chalk.metrics import summarize_events
from tests.test_llm_client import openai_auth_error, openai_response, patch_openai

RUBRIC = "1. Definition of a server - 20 points\n2. Server examples - 10 points"
SUBMISSION = "A server provides resources to other computers. Examples: web and mail servers."


def _reply(earned):
    return openai_response(
        text=json.dumps({"earned": earned, "reasoning": "Clear and correct.", "deduction_comment": ""}),
        input_tokens=1000,
        output_tokens=100,
    )


@pytest.fixture(autouse=True)
def provider(monkeypatch):
    for key, value in {"LLM_PROVIDER": "openai", "LLM_API_KEY": "sk", "LLM_MODEL": "gpt-4o"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)


def _grading_events(paths):
    return [
        e for e in metrics.read_events_by_type(paths.eval_log, "generation")
        if e["content_type"] == GRADING_CONTENT_TYPE
    ]


def test_a_grading_logs_its_calls_tokens_and_cost(tmp_project, monkeypatch):
    patch_openai(monkeypatch, [_reply(20), _reply(10)])

    result = grade_and_log(tmp_project, SUBMISSION, RUBRIC)

    assert result["earned_total"] == 30
    [event] = _grading_events(tmp_project)
    assert (event["ai_calls"], event["input_tokens"], event["output_tokens"]) == (2, 2000, 200)
    assert event["cost_usd"] == pytest.approx(2.0 * 0.0025 + 0.2 * 0.010)
    assert (event["criterion_count"], event["succeeded"], event["model"]) == (2, True, "gpt-4o")


def test_the_log_never_holds_the_submission_or_rubric(tmp_project, monkeypatch):
    patch_openai(monkeypatch, [_reply(20), _reply(10)])
    grade_and_log(tmp_project, SUBMISSION, RUBRIC)

    log = tmp_project.eval_log.read_text(encoding="utf-8")
    for content in ("resources to other computers", "Definition of a server", "Clear and correct"):
        assert content not in log


def test_grading_cost_counts_in_the_project_total(tmp_project, monkeypatch):
    patch_openai(monkeypatch, [_reply(20), _reply(10)])
    grade_and_log(tmp_project, SUBMISSION, RUBRIC)

    summary = summarize_events(metrics.read_events(tmp_project.eval_log))

    assert summary.total_cost_usd == pytest.approx(0.007)
    assert summary.generation_counts == {GRADING_CONTENT_TYPE: 1}


def test_a_grading_that_fails_partway_is_still_logged(tmp_project, monkeypatch):
    patch_openai(monkeypatch, [_reply(20), openai_auth_error()])

    with pytest.raises(LLMProviderError):
        grade_and_log(tmp_project, SUBMISSION, RUBRIC)

    [event] = _grading_events(tmp_project)
    assert (event["ai_calls"], event["succeeded"], event["criterion_count"]) == (1, False, None)


def test_a_grading_that_fails_before_any_call_logs_nothing(tmp_project):
    with pytest.raises(ValueError, match="cannot be empty"):
        grade_and_log(tmp_project, "  ", RUBRIC)

    assert _grading_events(tmp_project) == []
