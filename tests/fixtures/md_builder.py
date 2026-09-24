"""Programmatic synthetic .md builders for markdown extractor tests.

Mirrors tests/fixtures/docx_builder.py's approach: the smallest markdown
document that exercises one parsing rule, per DECISIONS.md.
"""

from __future__ import annotations

from pathlib import Path

_DEFAULT_FIELDS = {
    "Course": "IS 4490 Emerging Technologies",
    "Course Number": "IS 4490",
    "Section": "001",
    "Credits": "3",
    "Term": "Fall 2026",
    "Instructor": "Matt Pecsok",
    "Meeting Pattern": "In-person",
}


def _front_matter(**overrides) -> str:
    fields = dict(_DEFAULT_FIELDS)
    for key, value in overrides.items():
        if value is None:
            fields.pop(key, None)
        else:
            fields[key] = value
    return "\n".join(f"{label}: {value}" for label, value in fields.items()) + "\n"


def build_minimal_syllabus(path: Path) -> Path:
    content = _front_matter() + (
        "\n"
        "## Learning Objectives\n"
        "\n"
        "- Understand the fundamentals of IT network infrastructure\n"
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | 8/24 - 8/30 | Course Introduction | Reading 1 Due |\n"
        "| - | 10/10 - 10/18 | Fall Break |  |\n"
        "| 2 | 10/19 - 10/25 | Networking Basics | Lab 1 Due |\n"
        "\n"
        "| Assessment | Weight |\n"
        "| --- | --- |\n"
        "| Quizzes | 10% |\n"
        "| Final Project | 30% |\n"
        "\n"
        "| Event | Date |\n"
        "| --- | --- |\n"
        "| Classes begin | 8/24/2026 |\n"
        "| Fall Break | 10/10 - 10/18 |\n"
        "| Classes end | 12/10/2026 |\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_with_stray_line_after_objectives(path: Path) -> Path:
    """A non-bullet, non-heading line right after the objectives list, so
    the collector's "unexpected line" stop condition gets exercised."""
    content = _front_matter() + (
        "\n"
        "## Learning Objectives\n"
        "\n"
        "- Understand the fundamentals of IT network infrastructure\n"
        "This line is not a bullet and not a heading.\n"
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | 8/24 - 8/30 | Course Introduction |  |\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_with_alternate_objectives_heading(path: Path) -> Path:
    content = _front_matter() + (
        "\n"
        "# Course Outcome and Objectives\n"
        "\n"
        "- Understand the fundamentals of IT network infrastructure\n"
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | 8/24 - 8/30 | Course Introduction |  |\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_without_optional_sections(path: Path) -> Path:
    """No objectives, no assessments table, no university dates table —
    only what the PRD's markdown-path bullet list actually requires."""
    content = _front_matter() + (
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | 8/24 - 8/30 | Course Introduction |  |\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_with_no_schedule_table(path: Path) -> Path:
    content = _front_matter() + "\nThis document has no schedule table at all.\n"
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_with_multiple_candidate_tables(path: Path) -> Path:
    content = _front_matter() + (
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | 8/24 - 8/30 | Course Introduction |  |\n"
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | 8/24 - 8/30 | Duplicate table for ambiguity test |  |\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_with_unresolvable_break_row(path: Path) -> Path:
    content = _front_matter() + (
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | 8/24 - 8/30 | Course Introduction |  |\n"
        "| - | TBD | Fall Break |  |\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_with_unparseable_week_number(path: Path) -> Path:
    content = _front_matter() + (
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| one | 8/24 - 8/30 | Course Introduction |  |\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_with_unparseable_week_date(path: Path) -> Path:
    content = _front_matter() + (
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | TBD | Course Introduction |  |\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_missing_front_matter_field(path: Path, *, omit: str) -> Path:
    """`omit` is one of the keys in _DEFAULT_FIELDS, e.g. "Term"."""
    content = _front_matter(**{omit: None}) + (
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | 8/24 - 8/30 | Course Introduction |  |\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_with_invalid_credits(path: Path) -> Path:
    content = _front_matter(Credits="three") + (
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | 8/24 - 8/30 | Course Introduction |  |\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_with_unparseable_term_year(path: Path) -> Path:
    content = _front_matter(Term="Fall Semester") + (
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | 8/24 - 8/30 | Course Introduction |  |\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_with_unparseable_assessment_weight(path: Path) -> Path:
    content = _front_matter() + (
        "\n"
        "| Week | Dates | Topic | Major Work |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | 8/24 - 8/30 | Course Introduction |  |\n"
        "\n"
        "| Assessment | Weight |\n"
        "| --- | --- |\n"
        "| Final Project | TBD |\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def build_syllabus_with_invalid_encoding(path: Path) -> Path:
    path.write_bytes(b"\xff\xfe\x00\x01invalid utf-8 bytes \x80\x81")
    return path
