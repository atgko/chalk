"""A compact "Jump to…" dropdown on the course line.

Its workflows are listed in the order of the tab groups (Build, Grading
Assistant, Settings; ui/session.py), and picking one opens its group too.

Typing filters the list, and picking a workflow opens its tab right
away (preselecting the content type for a Generate workflow). The
dropdown only filters on the labels it shows, so each label carries the
words an instructor would type for it ("Canvas", "PowerPoint").
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from ui import session

_JUMP_KEY = "chalk_jump_to"
_JUMP_WIDTH = 280


@dataclass(frozen=True)
class Workflow:
    key: str
    label: str
    tab: str
    generation_type: str | None = None


WORKFLOWS = (
    Workflow("upload-syllabus", "Upload a syllabus", "Upload"),
    Workflow("review-course", "Review course details and schedule", "Review"),
    Workflow("rollover-course", "Roll over to a new term or 5-week sessions", "Rollover"),
    Workflow("generate-quiz", "Generate a quiz", "Generate", "quiz"),
    Workflow("generate-discussion", "Generate discussion prompts", "Generate", "discussion"),
    Workflow("generate-assignment", "Generate an assignment", "Generate", "assignment"),
    Workflow("generate-rubric", "Generate a rubric", "Generate", "rubric"),
    Workflow("generate-summary", "Generate a module summary", "Generate", "summary"),
    Workflow("generate-slides", "Generate slides (PowerPoint)", "Generate", "slides"),
    Workflow("view-drafts", "View saved drafts", "Drafts"),
    Workflow("export-canvas", "Export for Canvas", "Export"),
    Workflow("grade-submission", "Grade a student submission", "Grading Assistant"),
    Workflow("provider-settings", "Change AI provider settings", "AI Provider"),
    Workflow("view-metrics", "View costs and usage", "Metrics"),
)

_BY_KEY = {workflow.key: workflow for workflow in WORKFLOWS}


def render() -> None:
    """Draw the dropdown. Call it before the tabs render: the jump runs
    as a callback, ahead of the script, so the tab request lands in time."""
    st.selectbox(
        "Jump to",
        list(_BY_KEY),
        index=None,
        format_func=lambda key: _BY_KEY[key].label,
        key=_JUMP_KEY,
        on_change=_jump,
        placeholder="Jump to…",
        label_visibility="collapsed",
        width=_JUMP_WIDTH,
    )


def _jump() -> None:
    workflow = _BY_KEY.get(st.session_state.get(_JUMP_KEY))
    if workflow is None:
        return
    session.go_to_tab(workflow.tab)
    if workflow.generation_type is not None:
        session.set_generation_content_type(workflow.generation_type)
    st.session_state[_JUMP_KEY] = None
