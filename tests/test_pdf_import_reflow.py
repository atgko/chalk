"""Unit tests for chalk.pdf_import.reflow: rejoining a PDF's wrapped lines
into paragraphs."""

import pytest

from chalk.pdf_import.reflow import (
    Line,
    ends_in_url,
    is_bullet,
    is_caps_heading,
    join_wrapped,
    reflow_lines,
    strip_bullet,
)

CHAR = 5.0  # points per character in these hand-made lines
LEFT = 72.0
RIGHT_EDGE = LEFT + 60 * CHAR  # a 60-character column


def _lines(*texts, gap_after=()):
    """Lines stacked 12pt apart (an extra 12pt after the indexes in
    `gap_after`), each as wide as its text at CHAR points per letter."""
    lines, top = [], 100.0
    for index, text in enumerate(texts):
        lines.append(Line(text, LEFT, LEFT + len(text) * CHAR, top, top + 10))
        top += 24 if index in gap_after else 12
    return lines


def _texts(lines, right_edge=RIGHT_EDGE):
    return [text for _, text in reflow_lines(lines, right_edge)]


def test_a_full_line_continues_into_the_next():
    full = "Project management has become a way of life in many fields;"
    assert _texts(_lines(full, "Whether it is a merger or a new tool.")) == [
        "Project management has become a way of life in many fields; Whether it is a merger or a new tool."
    ]


def test_a_line_that_ended_with_room_to_spare_ends_its_paragraph():
    assert _texts(_lines("Professors: Ada Lovelace", "Phone: 555-0100")) == [
        "Professors: Ada Lovelace",
        "Phone: 555-0100",
    ]


def test_the_measured_width_of_the_next_word_decides_when_known():
    # The previous line ends 40pt short of the edge. An estimated 6-letter
    # word (30pt + a space) would fit, but the measured word is 45pt wide.
    previous = Line("x" * 52, LEFT, RIGHT_EDGE - 40, 100, 110)
    wide = Line("Management of change", LEFT, LEFT + 100, 112, 122, first_word_width=45)
    narrow = Line("Management of change", LEFT, LEFT + 100, 112, 122, first_word_width=20)
    assert len(_texts([previous, wide])) == 1
    assert len(_texts([previous, narrow])) == 2


def test_bullets_headings_and_sentence_ends_start_new_paragraphs():
    full = "a" * 59
    assert len(_texts(_lines(full, "• Second bullet"))) == 2
    assert len(_texts(_lines("CONTACT", "Professors: Ada"))) == 2
    assert len(_texts(_lines(full + ".", "Next sentence"))) == 2


def test_a_caps_word_after_a_full_line_is_a_wrapped_word_not_a_heading():
    assert _texts(_lines("Transforming the Work Environment for Front-Liners at the", "NUH”")) == [
        "Transforming the Work Environment for Front-Liners at the NUH”"
    ]


def test_a_lowercase_line_always_continues_and_a_vertical_gap_always_breaks():
    assert _texts(_lines("We discuss three phases of project management:", "conception and closure.")) == [
        "We discuss three phases of project management: conception and closure."
    ]
    full = "a" * 59
    assert len(_texts(_lines(full, "b" * 10, gap_after={0}))) == 2


def test_a_wrapped_url_is_rejoined_without_a_space():
    lines = _lines("https://www.projectmanageme", "nt.com/articles/749853")
    assert _texts(lines) == ["https://www.projectmanagement.com/articles/749853"]


def test_reflow_defaults_the_edge_to_the_widest_line_and_reports_tops():
    lines = _lines("Short", "Then a much longer line of text")
    assert reflow_lines(lines) == [(100.0, "Short"), (112.0, "Then a much longer line of text")]
    assert reflow_lines([]) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("● Item", True),
        ("•Item", True),
        ("- Item", True),
        ("-scope-creep--how", False),  # a wrapped URL, not a bullet
        ("●", False),
        ("Item", False),
    ],
)
def test_is_bullet(text, expected):
    assert is_bullet(text) is expected


def test_strip_bullet_and_caps_heading():
    assert strip_bullet("●  Distinguish projects") == "Distinguish projects"
    assert is_caps_heading("COURSE DESCRIPTION")
    assert not is_caps_heading("Course Description")
    assert not is_caps_heading("2026")
    assert not is_caps_heading("A" * 61)


def test_join_wrapped_and_urls():
    assert join_wrapped("organizational-", "wide") == "organizational-wide"
    assert join_wrapped("Readings -", "linked") == "Readings - linked"
    assert join_wrapped("see www.utah.edu/abc", "def") == "see www.utah.edu/abcdef"
    assert join_wrapped("Read the", "case") == "Read the case"
    assert ends_in_url("https://hbr.org/x")
    assert not ends_in_url("plain words")
