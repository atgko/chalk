"""Tests for chalk.course_brief (F-04)."""

import chalk.llm_client
from chalk.course_brief import render_course_brief, write_course_brief
from chalk.models import CourseData
from tests.sample_course import build_sample_course_data


def test_heading_is_the_course_title():
    brief = render_course_brief(build_sample_course_data())
    assert brief.startswith("# IS 6640 Networking and Servers\n")


def test_includes_every_course_info_field_the_prd_lists():
    brief = render_course_brief(build_sample_course_data())
    for expected in (
        "IS 6640",
        "Section 090",
        "Fall 2026",
        "10 weeks",
        "**Credits:** 3",
        "Online async",
        "Dave Norwood",
    ):
        assert expected in brief


def test_lists_learning_objectives_numbered():
    brief = render_course_brief(build_sample_course_data())
    assert "1. Understand the fundamentals of IT network infrastructure" in brief
    assert "2. Configure and secure Linux servers" in brief


def test_lists_assessment_weights_as_percentages():
    brief = render_course_brief(build_sample_course_data())
    assert "| Video Quizzes | 5% |" in brief
    assert "| Labs | 25% |" in brief


def test_condensed_schedule_has_one_line_per_week_with_joined_topics():
    brief = render_course_brief(build_sample_course_data())
    assert "| 1 | Aug 24 | Topic 1A; Topic 1B |" in brief
    assert "| 10 | Oct 26 | Topic 10A; Topic 10B |" in brief
    assert "| — | Oct 10 – Oct 18 | Fall Break |" in brief


def test_empty_sections_say_so_instead_of_rendering_blank_tables():
    course_data = build_sample_course_data().model_copy(
        update={"learning_objectives": [], "assessments": []}
    )
    brief = render_course_brief(course_data)
    assert brief.count("_None listed in the syllabus._") == 2
    assert "| Assessment | Weight |" not in brief


def test_pipe_characters_in_content_do_not_break_the_tables():
    course_data = build_sample_course_data()
    first_week = course_data.weeks[0].model_copy(update={"topics": ["TCP | UDP"]})
    course_data = course_data.model_copy(update={"weeks": [first_week, *course_data.weeks[1:]]})

    brief = render_course_brief(course_data)

    assert "| 1 | Aug 24 | TCP \\| UDP |" in brief


def test_week_with_no_topics_shows_a_dash():
    course_data = build_sample_course_data()
    first_week = course_data.weeks[0].model_copy(update={"topics": []})
    course_data = course_data.model_copy(update={"weeks": [first_week, *course_data.weeks[1:]]})

    assert "| 1 | Aug 24 | — |" in render_course_brief(course_data)


def test_never_calls_the_llm(monkeypatch):
    def _fail(*args, **kwargs):  # pragma: no cover - only runs if the brief wrongly calls the LLM
        raise AssertionError("course brief must not call the LLM")

    monkeypatch.setattr(chalk.llm_client, "complete", _fail)
    render_course_brief(build_sample_course_data())


def test_does_not_mutate_the_input(monkeypatch):
    course_data = build_sample_course_data()
    before = course_data.model_dump_json()
    render_course_brief(course_data)
    assert CourseData.model_validate_json(before) == course_data


def test_write_creates_the_file_and_archives_the_previous_version(tmp_path):
    output_path = tmp_path / "outputs" / "course-brief.md"
    course_data = build_sample_course_data()

    write_course_brief(course_data, output_path)
    write_course_brief(course_data, output_path)

    assert output_path.read_text(encoding="utf-8") == render_course_brief(course_data)
    assert len(list((output_path.parent / ".archive").iterdir())) == 1


def test_break_rows_do_not_repeat_the_dates_embedded_in_their_label():
    course_data = build_sample_course_data()
    weeks = [
        w.model_copy(update={"label": "Fall Break (10/10 - 10/18)"}) if w.is_break else w
        for w in course_data.weeks
    ]
    brief = render_course_brief(course_data.model_copy(update={"weeks": weeks}))
    assert "| — | Oct 10 – Oct 18 | Fall Break |" in brief
