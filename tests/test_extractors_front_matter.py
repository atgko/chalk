import pytest

from chalk.errors import ExtractionError
from chalk.extractors._front_matter import finalize_front_matter, parse_labeled_line


def test_parse_labeled_line_recognizes_a_known_field():
    assert parse_labeled_line("Term: Fall 2026") == ("term", "Fall 2026")


def test_parse_labeled_line_ignores_an_unrecognized_label():
    # A colon-containing line that isn't one of our known front-matter
    # labels — e.g. a topic like "Networking: fundamentals of
    # infrastructure" showing up outside the schedule table.
    assert parse_labeled_line("Networking: fundamentals of infrastructure") is None


def test_parse_labeled_line_ignores_a_line_with_no_colon():
    assert parse_labeled_line("This is just a sentence.") is None


def test_finalize_front_matter_raises_when_fields_are_missing():
    with pytest.raises(ExtractionError) as exc_info:
        finalize_front_matter({"title": "IS 6640"})

    assert "term" in exc_info.value.user_message
