import json

import pytest

from chalk.grading import criterion

RUBRIC = "1. Definition of a server - 20 points"
CRITERION = {"name": "Definition of a server", "possible": 20}


def test_valid_grading_response(monkeypatch):
    def fake_complete(*args, **kwargs):
        return {
            "text": json.dumps({
                "earned": 18,
                "reasoning": "The definition is mostly correct.",
                "deduction_comment": "Clarify the server's role.",
            })
        }

    monkeypatch.setattr(criterion, "complete", fake_complete)

    result = criterion.grade_criterion(
        "A server provides resources to other computers.",
        RUBRIC,
        CRITERION,
    )

    assert result["earned"] == 18
    assert result["possible"] == 20
    assert result["deduction_comment"] == "Clarify the server's role."


def test_invalid_json_response(monkeypatch):
    monkeypatch.setattr(
        criterion,
        "complete",
        lambda *args, **kwargs: {"text": ""},
    )

    with pytest.raises(ValueError, match="invalid grading JSON twice"):
        criterion.grade_criterion("Test submission", RUBRIC, CRITERION)


def test_score_exceeding_maximum(monkeypatch):
    monkeypatch.setattr(
        criterion,
        "complete",
        lambda *args, **kwargs: {
            "text": json.dumps({
                "earned": 25,
                "reasoning": "Excellent work.",
                "deduction_comment": "",
            })
        },
    )

    with pytest.raises(ValueError, match="outside the rubric range"):
        criterion.grade_criterion("Test submission", RUBRIC, CRITERION)


def test_retry_succeeds_after_invalid_json(monkeypatch):
    responses = iter([
        {"text": ""},
        {
            "text": (
                '{"earned": 18, '
                '"reasoning": "The definition is mostly correct.", '
                '"deduction_comment": "Clarify the server role."}'
            )
        },
    ])
    calls = []

    def fake_complete(*args, **kwargs):
        calls.append(1)
        return next(responses)

    monkeypatch.setattr(criterion, "complete", fake_complete)

    result = criterion.grade_criterion(
        "A server provides resources to other computers.",
        RUBRIC,
        CRITERION,
    )

    assert result["earned"] == 18
    assert result["possible"] == 20
    assert len(calls) == 2
