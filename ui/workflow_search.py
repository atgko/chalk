"""Searchable shortcuts to Chalk tabs and common workflows.

The empty search shows a small set of popular starting points. As soon
as the instructor types, those are replaced by matching workflows.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from ui import session

_SEARCH_KEY = "chalk_workflow_search"
_CLEAR_SEARCH_KEY = "chalk_clear_workflow_search"


@dataclass(frozen=True)
class Workflow:
    key: str
    label: str
    tab: str
    description: str
    search_terms: tuple[str, ...]
    generation_type: str | None = None


WORKFLOWS = (
    Workflow(
        "upload-syllabus",
        "Upload a syllabus",
        "Upload",
        "Add a Word, Markdown, or PDF syllabus.",
        ("upload", "syllabus", "pdf", "word", "document", "extract"),
    ),
    Workflow(
        "review-course",
        "Review course information",
        "Review",
        "Check extracted course details, objectives, grading, and schedule.",
        ("review", "course", "details", "objectives", "grading", "schedule"),
    ),
    Workflow(
        "rollover-course",
        "Update a course for a new term",
        "Rollover",
        "Change semester dates or course length with a preview first.",
        ("rollover", "update", "term", "semester", "dates", "schedule", "length"),
    ),
    Workflow(
        "generate-quiz",
        "Quiz generation",
        "Generate",
        "Open Generate with Quiz selected.",
        ("quiz", "questions", "test", "assessment", "generate", "create"),
        "quiz",
    ),
    Workflow(
        "generate-discussion",
        "Discussion prompt generation",
        "Generate",
        "Open Generate with Discussion prompts selected.",
        ("discussion", "prompt", "forum", "generate", "create"),
        "discussion",
    ),
    Workflow(
        "generate-assignment",
        "Assignment generation",
        "Generate",
        "Open the Assignment creator and enhancer.",
        ("assignment", "activity", "instructions", "enhance", "generate", "create"),
        "assignment",
    ),
    Workflow(
        "generate-rubric",
        "Rubric generation",
        "Generate",
        "Open Generate with Rubric selected.",
        ("rubric", "criteria", "points", "grading", "generate", "create"),
        "rubric",
    ),
    Workflow(
        "generate-summary",
        "Module summary generation",
        "Generate",
        "Open Generate with Module summary selected.",
        ("summary", "module", "overview", "generate", "create"),
        "summary",
    ),
    Workflow(
        "generate-slides",
        "Slide outline generation",
        "Generate",
        "Open Generate with Slides selected.",
        ("slides", "presentation", "powerpoint", "outline", "generate", "create"),
        "slides",
    ),
    Workflow(
        "export-canvas",
        "Prepare content for Canvas",
        "Export",
        "Create and copy Canvas-ready HTML or download course outputs.",
        ("canvas", "export", "html", "copy", "download", "output"),
    ),
    Workflow(
        "view-metrics",
        "View activity and costs",
        "Metrics",
        "Review generation costs, rollovers, and evaluation results.",
        ("metrics", "cost", "usage", "report", "evaluation", "activity"),
    ),
    Workflow(
        "provider-settings",
        "Change AI provider settings",
        "Settings",
        "Connect or change OpenAI, Claude, Gemini, or a local model.",
        ("settings", "provider", "openai", "chatgpt", "claude", "gemini", "ollama", "model"),
    ),
)

_POPULAR_KEYS = ("upload-syllabus", "review-course", "rollover-course", "generate-quiz")


def search_workflows(query: str) -> list[Workflow]:
    """Return workflows containing every word the instructor typed."""
    words = query.casefold().split()
    if not words:
        return [workflow for workflow in WORKFLOWS if workflow.key in _POPULAR_KEYS]
    matches = []
    for workflow in WORKFLOWS:
        haystack = " ".join(
            (workflow.label, workflow.tab, workflow.description, *workflow.search_terms)
        ).casefold()
        if all(word in haystack for word in words):
            matches.append(workflow)
    return matches


def render(*, course_ready: bool) -> None:
    """Draw the search and route a selected result before tabs render."""
    if st.session_state.pop(_CLEAR_SEARCH_KEY, False):
        st.session_state[_SEARCH_KEY] = ""

    with st.container(border=True):
        query = st.text_input(
            "Search Chalk workflows",
            key=_SEARCH_KEY,
            placeholder="Try Quiz, Canvas, update dates, rubric…",
            help="Describe what you want to do; you do not need to know which tab it is on.",
        )
        if not course_ready:
            st.warning(
                "**Upload your syllabus first.** Generation workflows such as quizzes, "
                "assignments, and rubrics need a saved course to work from. Open **Upload**, "
                "choose **Extract course**, then check the result under **Review** and select "
                "**Confirm and save** before generating content."
            )
        matches = search_workflows(query)
        if query.strip():
            st.caption("Matching workflows")
        else:
            st.caption("Suggested workflows")

        if not matches:
            st.info(
                "No matching workflow. Try a simpler word such as quiz, syllabus, "
                "Canvas, or settings."
            )
            return

        columns = st.columns(min(4, len(matches)))
        for index, workflow in enumerate(matches[:8]):
            column = columns[index % len(columns)]
            if column.button(
                workflow.label,
                key=f"workflow-{workflow.key}",
                help=f"{workflow.description} Opens the {workflow.tab} tab.",
                use_container_width=True,
            ):
                session.go_to_tab(workflow.tab)
                if workflow.generation_type is not None:
                    session.set_generation_content_type(workflow.generation_type)
                session.flash(f"Opened {workflow.label}.")
                st.session_state[_CLEAR_SEARCH_KEY] = True
                st.rerun()
