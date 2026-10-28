"""Tests for Chalk's Assignment Creator / Enhancer."""
import pytest

from chalk.errors import GenerationError
from chalk.generation.engine import GenerationRequest, build_prompt, output_path_for
from chalk.generation.specs import SPECS
from tests.sample_course import build_sample_course_data


def test_assignment_spec():
    spec = SPECS["assignment"]
    assert spec.per_week is False
    assert spec.output_subdir == "assignments"

def test_create_assignment_prompt(tmp_project):
    course = build_sample_course_data()
    request = GenerationRequest(
        "assignment",
        assignment_mode="create",
        assignment_name="Network Recommendation",
        assignment_goal="Apply networking concepts to a business decision",
        assignment_requirements="Students must defend their recommendation",
    )
    prompt = build_prompt(tmp_project, course, request)
    assert "ASSIGNMENT MODE:" in prompt
    assert "create" in prompt
    assert "Network Recommendation" in prompt
    assert "Configure and secure Linux servers" in prompt
    assert "Students must defend their recommendation" in prompt
    assert "The materials above are REFERENCE CONTEXT" in prompt
    assert "Create the assignment now" in prompt
    assert "Do not ask the instructor a follow-up question" in prompt

def test_enhance_requires_existing_assignment(tmp_project):
    course = build_sample_course_data()
    request = GenerationRequest(
        "assignment",
        assignment_mode="enhance",
        assignment_name="Lab 1",
        assignment_goal="Apply the week's concepts",
    )
    with pytest.raises(GenerationError, match="existing assignment"):
        build_prompt(tmp_project, course, request)

def test_assignment_output_path(tmp_project):
    request = GenerationRequest(
        "assignment",
        assignment_name="Network Design: Recommendation!",
        assignment_goal="Make a recommendation",
    )
    assert output_path_for(tmp_project, request) == (
        tmp_project.root / "outputs/assignments/network-design-recommendation-assignment.md"
    )
