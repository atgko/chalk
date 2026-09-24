"""Shared pytest fixtures for the Chalk test suite.

Fixtures are added incrementally as each milestone introduces the objects
they need: sample_course_data, tmp_project_dir, synthetic_docx_factory,
synthetic_md_factory, mock_llm_client, frozen_time. See PLAN.md Section 5
("Test Strategy") for the full fixture-to-task map.
"""

import pytest

from chalk.project import init_project


@pytest.fixture
def tmp_project(tmp_path):
    """A freshly `init`-ed course project under tmp_path, seeded from the
    real bundled resources (config.json, calendars.json)."""
    return init_project(tmp_path, "IS-6640-Test")
