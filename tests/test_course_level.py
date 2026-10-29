"""Course level and the AI-use component (chalk/generation/course_level.py),
and how they reach the prompt."""

import pytest

from chalk.errors import GenerationError
from chalk.generation.course_level import (
    AI_COMPONENT_GUIDANCE,
    AI_TASK_HEADING,
    GRADUATE,
    LOWER_DIVISION,
    UPPER_DIVISION,
    has_ai_task_section,
    level_from_course_number,
    level_guidance,
)
from chalk.generation.engine import GenerationRequest, build_prompt
from tests.sample_course import build_sample_course_data


@pytest.mark.parametrize(
    ("number", "level"),
    [
        ("IS 1010", LOWER_DIVISION),
        ("IS 2999", LOWER_DIVISION),
        ("IS 3000", UPPER_DIVISION),
        ("IS 4490", UPPER_DIVISION),
        ("IS 5999", UPPER_DIVISION),
        ("IS 6640", GRADUATE),
        ("OSC6660", GRADUATE),
        ("IS 66401", None),  # not a four-digit course number
        ("", None),
        ("Special Topics", None),
    ],
)
def test_level_from_the_u_of_u_course_number(number, level):
    assert level_from_course_number(number) == level


def test_no_level_adds_no_guidance():
    assert level_guidance(None) == ""


def test_each_level_has_its_own_guidance():
    texts = {level_guidance(level) for level in (LOWER_DIVISION, UPPER_DIVISION, GRADUATE)}
    assert len(texts) == 3
    assert level_guidance(GRADUATE).startswith("COURSE LEVEL: graduate.")


def test_an_unknown_level_is_a_plain_error():
    with pytest.raises(GenerationError, match="Course level must be one of"):
        level_guidance("doctoral")


# ---- In the prompt ------------------------------------------------------------------


@pytest.fixture
def course():
    return build_sample_course_data()


def _assignment(**kwargs) -> GenerationRequest:
    return GenerationRequest("assignment", assignment_name="Design Brief", assignment_goal="Defend a design.", **kwargs)


def test_the_level_goes_where_the_template_asks(tmp_project, course):
    prompt = build_prompt(tmp_project, course, GenerationRequest("quiz", week_number=3, course_level=GRADUATE))

    assert prompt.index(level_guidance(GRADUATE)) < prompt.index("Generate 5 questions")
    assert "{course_level_guidance}" not in prompt


def test_no_level_leaves_no_trace_in_the_prompt(tmp_project, course):
    prompt = build_prompt(tmp_project, course, GenerationRequest("quiz", week_number=3))
    assert "COURSE LEVEL" not in prompt
    assert "{course_level_guidance}" not in prompt


def test_an_older_template_gets_the_level_at_the_end(tmp_project, course):
    (tmp_project.prompts_dir / "quiz.txt").write_text(
        "Quiz for {course_title}, week {week_number}: {topics}. {learning_objectives} "
        "{question_count} {format} {source_material_context}\n",
        encoding="utf-8",
    )

    prompt = build_prompt(tmp_project, course, GenerationRequest("quiz", week_number=3, course_level=LOWER_DIVISION))

    assert prompt.startswith("Quiz for ")
    assert prompt.rstrip().endswith(level_guidance(LOWER_DIVISION))


def test_an_assignment_can_ask_for_an_ai_use_component(tmp_project, course):
    with_ai = build_prompt(tmp_project, course, _assignment(include_ai_component=True))
    without = build_prompt(tmp_project, course, _assignment())

    assert AI_COMPONENT_GUIDANCE in with_ai
    assert "AI-USE COMPONENT" not in without
    assert "{ai_component_guidance}" not in without


def test_only_assignments_get_the_ai_use_component(tmp_project, course):
    prompt = build_prompt(tmp_project, course, GenerationRequest("quiz", week_number=3, include_ai_component=True))
    assert "AI-USE COMPONENT" not in prompt


# ---- Finding the AI-use task (sponsor meeting, Oct 28) ------------------------------


def test_the_ai_task_goes_in_its_own_labeled_section():
    assert f"## {AI_TASK_HEADING}" in AI_COMPONENT_GUIDANCE
    assert "(AI-use task)" in AI_COMPONENT_GUIDANCE


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("# Lab\n\n## MORE DETAILS\n...\n\n## AI-USE TASK\n> This task asks you to use AI.\n", True),
        ("# Lab\n\n## AI-Use Task\nUse an AI tool.\n", True),
        ("# Lab\n\n## MORE DETAILS\n3. Use an AI tool to brainstorm.\n", False),
    ],
)
def test_has_ai_task_section(text, expected):
    assert has_ai_task_section(text) is expected
