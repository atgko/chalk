"""Grounding a grading in the submission (BACKLOG.md, "Make grading
consistent"): a low temperature, and a quote from the submission behind
every score that Chalk checks is really there."""

import io
import json

import pytest

from chalk.grading import criterion, evidence_evaluator, workflow
from chalk.grading.export import evidence_lines, export_pdf, export_word
from chalk.grading.grounding import GRADING_TEMPERATURE, check_quote, quote_in_submission
from chalk.grading.scoring import calculate_scores

SUBMISSION = (
    "A server provides resources to other computers on a network.\n"
    "To secure it, I would apply patches   promptly and enable a firewall, "
    "which blocks unused ports."
)


# ---- Finding a quote in the submission ----------------------------------


def test_an_exact_quote_is_found():
    assert quote_in_submission("provides resources to other computers", SUBMISSION)


@pytest.mark.parametrize(
    "quote",
    [
        "Apply patches promptly",  # case and the submission's extra spaces
        '"enable a firewall."',  # quote marks and a closing period added
        "I would apply patches … which blocks unused ports",  # an ellipsis
        "I would apply patches ... which blocks unused ports",
        "which blocks unused ports",
    ],
)
def test_a_quote_copied_with_small_differences_is_still_found(quote):
    assert quote_in_submission(quote, SUBMISSION)


def test_curly_quotes_and_dashes_match_straight_ones():
    assert quote_in_submission("it’s a web–server", "It's a web-server.")


@pytest.mark.parametrize(
    "quote",
    [
        "uses multi-factor authentication",  # not in the submission
        "which blocks unused ports ... apply patches",  # fragments out of order
        "",
        "  ...  ",
    ],
)
def test_a_quote_that_isnt_in_the_submission_is_not_found(quote):
    assert not quote_in_submission(quote, SUBMISSION)


def test_check_quote_accepts_a_found_quote_without_a_note():
    assert check_quote("enable a firewall", SUBMISSION, earned=5) == ("enable a firewall", "")


def test_check_quote_flags_a_quote_missing_from_the_submission():
    quote, note = check_quote("uses multi-factor authentication", SUBMISSION, earned=5)
    assert quote == "uses multi-factor authentication"
    assert "wasn't found word for word in the submission" in note


def test_check_quote_flags_credit_with_no_quote():
    assert "No quote from the submission supports" in check_quote("", SUBMISSION, earned=5)[1]


def test_check_quote_accepts_zero_credit_with_no_quote():
    assert check_quote("", SUBMISSION, earned=0) == ("", "")


def test_check_quote_treats_a_non_text_quote_as_none():
    assert check_quote(None, SUBMISSION, earned=0) == ("", "")


# ---- One criterion at a time ---------------------------------------------

RUBRIC = "1. Definition of a server - 20 points"
CRITERION = {"name": "Definition of a server", "possible": 20}


def _criterion_reply(**fields):
    reply = {"earned": 18, "reasoning": "Mostly correct.", "deduction_comment": "Name an example."}
    return {"text": json.dumps({**reply, **fields})}


def test_criterion_grading_asks_for_a_quote_at_the_grading_temperature(monkeypatch):
    seen = {}

    def fake_complete(prompt, **kwargs):
        seen.update(kwargs, prompt=prompt)
        return _criterion_reply(evidence="provides resources to other computers")

    monkeypatch.setattr(criterion, "complete", fake_complete)

    result = criterion.grade_criterion(SUBMISSION, RUBRIC, CRITERION)

    assert seen["temperature"] == GRADING_TEMPERATURE == 0.0
    assert '"evidence"' in seen["prompt"] and "word for word" in seen["prompt"]
    assert result["evidence"] == ["provides resources to other computers"]
    assert result["evidence_note"] == ""


def test_criterion_grading_flags_a_quote_that_isnt_in_the_submission(monkeypatch):
    monkeypatch.setattr(
        criterion, "complete", lambda *args, **kwargs: _criterion_reply(evidence="servers run on Linux")
    )

    result = criterion.grade_criterion(SUBMISSION, RUBRIC, CRITERION)

    assert result["earned"] == 18  # the score is the instructor's call
    assert "wasn't found word for word" in result["evidence_note"]


def test_criterion_grading_flags_credit_when_the_reply_has_no_quote(monkeypatch):
    monkeypatch.setattr(criterion, "complete", lambda *args, **kwargs: _criterion_reply())

    result = criterion.grade_criterion(SUBMISSION, RUBRIC, CRITERION)

    assert result["evidence"] == []
    assert "No quote from the submission supports" in result["evidence_note"]


# ---- Explicitly weighted requirements --------------------------------------

WEIGHTED = {
    "name": "Server security",
    "possible": 10,
    "subrequirements": [
        {"name": "First practice", "possible": 5},
        {"name": "Second practice", "possible": 5},
    ],
}


def _evaluations(*items):
    return {"text": json.dumps({"evaluations": list(items)})}


def test_weighted_grading_asks_for_quotes_at_the_grading_temperature(monkeypatch):
    seen = {}

    def fake_complete(prompt, **kwargs):
        seen.update(kwargs, prompt=prompt)
        return _evaluations(
            {"met": True, "evidence": "Patching.", "quote": "apply patches promptly"},
            {"met": True, "evidence": "A firewall.", "quote": "enable a firewall"},
        )

    monkeypatch.setattr(evidence_evaluator, "complete", fake_complete)

    result = evidence_evaluator.evaluate_weighted_criterion(SUBMISSION, WEIGHTED)

    assert seen["temperature"] == GRADING_TEMPERATURE
    assert '"quote"' in seen["prompt"]
    assert result["earned"] == 10
    assert result["evidence"] == ["apply patches promptly", "enable a firewall"]
    assert result["evidence_note"] == ""


def test_weighted_grading_names_the_requirement_whose_quote_is_missing(monkeypatch):
    monkeypatch.setattr(
        evidence_evaluator,
        "complete",
        lambda *args, **kwargs: _evaluations(
            {"met": True, "evidence": "Patching.", "quote": "apply patches promptly"},
            {"met": True, "evidence": "MFA.", "quote": "requires multi-factor sign-in"},
        ),
    )

    result = evidence_evaluator.evaluate_weighted_criterion(SUBMISSION, WEIGHTED)

    assert result["earned"] == 10
    assert result["evidence_note"].startswith("Second practice: ")
    assert "First practice" not in result["evidence_note"]


def test_an_unmet_requirement_needs_no_quote(monkeypatch):
    monkeypatch.setattr(
        evidence_evaluator,
        "complete",
        lambda *args, **kwargs: _evaluations(
            {"met": True, "evidence": "Patching.", "quote": "apply patches promptly"},
            {"met": False, "evidence": "No second practice."},
        ),
    )

    result = evidence_evaluator.evaluate_weighted_criterion(SUBMISSION, WEIGHTED)

    assert result["earned"] == 5
    assert result["evidence"] == ["apply patches promptly"]
    assert result["evidence_note"] == ""


# ---- Carried through scoring and the whole grading -------------------------


def test_scoring_keeps_each_criterions_evidence():
    scores = calculate_scores([
        {"name": "A", "earned": 5, "possible": 5, "reasoning": "Good.",
         "evidence": ["a quote"], "evidence_note": ""},
        {"name": "B", "earned": 2, "possible": 5, "reasoning": "Partly.",
         "deduction_comment": "More.", "evidence_note": "Check it."},
    ])

    assert scores["criteria"][0]["evidence"] == ["a quote"]
    assert scores["criteria"][1]["evidence"] == []
    assert scores["criteria"][1]["evidence_note"] == "Check it."


def test_the_instructor_notes_list_the_criteria_whose_evidence_needs_checking(monkeypatch):
    monkeypatch.setattr(
        workflow,
        "grade_criterion",
        lambda submission, rubric, criterion, instructions="": {
            "name": criterion["name"], "possible": criterion["possible"], "earned": 3,
            "reasoning": "Partly.", "deduction_comment": "More.",
            "evidence": [], "evidence_note": "No quote from the submission supports this score.",
        },
    )

    result = workflow.analyze_by_criterion(SUBMISSION, "1. Definition - 5 points\n2. Examples - 5 points")

    assert "Check the quoted evidence for: Definition, Examples." in result["instructor_notes"]


# ---- In the downloaded reports ---------------------------------------------


def _graded(evidence, note=""):
    return {
        "earned_total": 3, "possible_total": 5, "percentage": 60.0,
        "criteria": [{"name": "Definition", "earned": 3, "possible": 5, "reasoning": "Partly.",
                      "deduction_comment": "More.", "evidence": evidence, "evidence_note": note}],
        "student_feedback": "Good start.", "instructor_notes": "",
    }


def test_evidence_lines_put_each_quote_then_the_note():
    criterion_result = _graded(["a <server> & more"], "Check it.")["criteria"][0]
    assert evidence_lines(criterion_result) == ['Evidence: "a <server> & more"', "Check it."]
    assert evidence_lines({"name": "Older result"}) == []


def test_the_word_report_shows_the_quote_and_the_note():
    from docx import Document

    data = export_word(_graded(["a <server> & more"], "Check it."))

    text = [p.text for p in Document(io.BytesIO(data)).paragraphs]
    assert 'Evidence: "a <server> & more"' in text and "Check it." in text


def test_the_pdf_report_shows_a_quote_with_markup_characters():
    import pdfplumber

    data = export_pdf(_graded(["a <server> & more"]))

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text = "".join(page.extract_text() for page in pdf.pages)
    assert 'Evidence: "a <server> & more"' in text
