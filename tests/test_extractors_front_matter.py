import pytest

from chalk.errors import ExtractionError
from chalk.extractors._front_matter import (
    extract_front_matter,
    parse_labeled_line,
    replace_term_text,
)


def test_parse_labeled_line_recognizes_a_known_field():
    assert parse_labeled_line("Term: Fall 2026") == ("term", "Fall 2026")


def test_parse_labeled_line_ignores_an_unrecognized_label():
    # A colon-containing line that isn't one of our known front-matter
    # labels — e.g. a topic like "Networking: fundamentals of
    # infrastructure" showing up outside the schedule table.
    assert parse_labeled_line("Networking: fundamentals of infrastructure") is None


def test_parse_labeled_line_ignores_a_line_with_no_colon():
    assert parse_labeled_line("This is just a sentence.") is None


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Professor:\t\tDave Norwood", ("instructor", "Dave Norwood")),
        ("Semester: Fall 2026", ("term", "Fall 2026")),
        ("Credit Hours: 3", ("credits", "3")),
        ("Class Meetings: Tue/Thu 9:10-10:30", ("meeting_pattern", "Tue/Thu 9:10-10:30")),
        ("Course Name: Networking and Servers", ("title", "Networking and Servers")),
        ("Course Code: IS 6640", ("number", "IS 6640")),
        ("**Instructor:** Dave Norwood", ("instructor", "Dave Norwood")),
    ],
)
def test_parse_labeled_line_accepts_common_label_variants(line, expected):
    assert parse_labeled_line(line) == expected


def test_labeled_lines_still_extract_every_field():
    fields = extract_front_matter(
        [
            "Course: IS 6640 Networking and Servers",
            "Course Number: IS 6640",
            "Section: 090",
            "Credits: 3",
            "Term: Fall 2026",
            "Instructor: Dave Norwood",
            "Meeting Pattern: Online async",
        ]
    )

    assert fields == {
        "title": "IS 6640 Networking and Servers",
        "number": "IS 6640",
        "section": "090",
        "credits": 3,
        "term": "Fall 2026",
        "instructor": "Dave Norwood",
        "meeting_pattern": "Online async",
    }


def test_free_form_header_like_a_real_syllabus_is_understood():
    fields = extract_front_matter(
        [
            "",
            "Networking and Servers – Online Fall 2026",
            "IS 6640, 10-week and IS 6445, Servers Only, 5-week",
            "CONTACT",
            "Professor:\t\tJane Example",
            "E-mail:\t\tjane@example.edu",
        ]
    )

    assert fields["title"] == "Networking and Servers – Online"
    assert fields["number"] == "IS 6640"
    assert fields["term"] == "Fall 2026"
    assert fields["instructor"] == "Jane Example"
    assert fields["section"] == ""
    assert fields["credits"] is None
    assert fields["meeting_pattern"] == ""


def test_markdown_heading_supplies_number_and_title():
    fields = extract_front_matter(["# IS 4490: Emerging Technologies", "Spring 2027 Syllabus"])

    assert fields["number"] == "IS 4490"
    assert fields["title"] == "Emerging Technologies"
    assert fields["term"] == "Spring 2027"


def test_labeled_values_win_over_header_guesses():
    fields = extract_front_matter(
        ["Networking and Servers Fall 2025", "Term: Fall 2026", "Title: Servers"]
    )

    assert fields["term"] == "Fall 2026"
    assert fields["title"] == "Servers"


def test_term_value_is_normalized_to_season_and_year():
    assert extract_front_matter(["Title: X", "Semester: Fall Semester 2026"])["term"] == "Fall 2026"


def test_all_caps_season_is_not_mistaken_for_a_course_number():
    fields = extract_front_matter(["NETWORKING AND SERVERS", "FALL 2026"])

    assert fields["number"] == ""
    assert fields["term"] == "Fall 2026"
    assert fields["title"] == "NETWORKING AND SERVERS"


def test_title_falls_back_to_the_course_number():
    fields = extract_front_matter(["Course Number: IS 6640", "Term: Fall 2026"])

    assert fields["title"] == "IS 6640"


@pytest.mark.parametrize(("raw", "expected"), [("3", 3), ("3 credit hours", 3), ("three", None)])
def test_credits_are_read_loosely(raw, expected):
    assert (
        extract_front_matter(["Title: X", "Term: Fall 2026", f"Credits: {raw}"])["credits"]
        == expected
    )


def test_missing_term_raises_a_helpful_error():
    with pytest.raises(ExtractionError) as exc_info:
        extract_front_matter(["Networking and Servers", "Professor: Jane Example"])

    assert "Term: Fall 2026" in exc_info.value.user_message


def test_a_term_mentioned_deep_in_the_body_is_not_used():
    lines = (
        ["Networking and Servers"] + ["Some policy text."] * 30 + ["Grades post after Fall 2026."]
    )

    with pytest.raises(ExtractionError):
        extract_front_matter(lines)


def test_replace_term_text_swaps_only_the_season_and_year():
    assert replace_term_text("Networking and Servers – Online Fall 2026", "Spring 2027") == (
        "Networking and Servers – Online Spring 2027"
    )
    assert (
        replace_term_text("Semester: Fall Semester 2026", "Spring 2027") == "Semester: Spring 2027"
    )
    assert replace_term_text("No term here", "Spring 2027") is None
