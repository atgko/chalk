import pytest

from chalk.errors import (
    AmbiguousTableError,
    ChalkError,
    ExtractionError,
    LLMProviderError,
    ProtectedFileError,
)


def test_chalk_error_carries_user_message():
    err = ChalkError("Something went wrong in plain English.")
    assert err.user_message == "Something went wrong in plain English."
    assert str(err) == "Something went wrong in plain English."


@pytest.mark.parametrize("exc_type", [LLMProviderError, ExtractionError, ProtectedFileError])
def test_subclasses_are_chalk_errors_and_preserve_user_message(exc_type):
    err = exc_type("A specific plain-English message.")
    assert isinstance(err, ChalkError)
    assert err.user_message == "A specific plain-English message."


def test_ambiguous_table_error_is_an_extraction_error_and_carries_candidates():
    candidates = ["Week 1 (8/24) | Course Intro...", "Grading | Weight | ..."]
    err = AmbiguousTableError(
        "Multiple possible schedule tables were found. Choose the correct one below.",
        candidates=candidates,
    )
    assert isinstance(err, ExtractionError)
    assert err.candidates == candidates


def test_ambiguous_table_error_supports_the_zero_candidates_not_found_case():
    err = AmbiguousTableError(
        "No schedule table found. Make sure your syllabus has a table with "
        "'Week' in the first column, then try again.",
        candidates=[],
    )
    assert err.candidates == []
