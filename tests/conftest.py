"""Shared pytest fixtures for the Chalk test suite.

Fixtures are added incrementally as each milestone introduces the objects
they need: sample_course_data, tmp_project_dir, synthetic_docx_factory,
synthetic_md_factory, mock_llm_client, frozen_time. See PLAN.md Section 5
("Test Strategy") for the full fixture-to-task map.
"""
