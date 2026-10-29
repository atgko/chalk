"""App shell: project resolution, first-run setup, the tabs (grouped as
Build, Grading Assistant, and Settings; ui/session.py), tab gating, and
the provider/cost footer (PRD section 7, DECISIONS.md).

Every tab renders inside `_guarded`, so no traceback ever reaches the
screen: ChalkErrors show their plain-English message, anything
unexpected shows a short notice and is logged to the terminal.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

import streamlit as st

from chalk import branding
from chalk.config import (
    adopt_project_provider,
    apply_provider_env,
    describe_provider,
    effective_env,
    env_is_configured,
)
from chalk.errors import ChalkError
from chalk.metrics import read_events, summarize_events
from chalk.models import CourseData
from chalk.project import ProjectPaths, load_course, open_project
from ui import (
    background,
    drafts_view,
    export_view,
    generate_view,
    grading_view,
    metrics_view,
    project_picker,
    review_view,
    rollover_view,
    session,
    settings_view,
    setup_view,
    upload_view,
    workflow_search,
)
from ui.common import render_header, render_needs_course

TAB_NAMES = tuple(tab for tabs in session.TAB_GROUPS.values() for tab in tabs)
# Tabs that work from a saved course: dimmed until there is one.
NEEDS_COURSE_TABS = ("Rollover", "Generate", "Export", "Metrics")

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    st.set_page_config(page_title=branding.PROJECT_NAME, page_icon="📘", layout="wide")

    paths = _resolve_project(sys.argv[1:] if argv is None else argv)
    if paths is None:
        project_picker.render()
        return

    adopt_project_provider(paths.env)
    apply_provider_env(paths.env)
    if not env_is_configured(paths.env) and not session.setup_skipped():
        setup_view.render(paths)
        return

    render_header(branding.PROJECT_NAME)
    _render_course_line(paths)
    message = session.pop_flash()
    if message:
        st.success(message)
    background.show_toasts()

    course_data = _load_course_or_warn(paths)
    session.apply_tab_request()
    background.clear_mark(session.active_tab())
    build_group, grading, settings_group = st.tabs(
        tuple(session.TAB_GROUPS), key=session.GROUP_TAB_KEY, on_change=session.on_group_change
    )
    with build_group:
        upload, review, rollover, generate, drafts, export = _sub_tabs("Build")
    with settings_group:
        settings, metrics = _sub_tabs("Settings")
    with upload:
        _guarded(upload_view.render, paths)
    with review:
        _guarded(review_view.render, paths, course_data)
    for tab, name, view in (
        (rollover, "Rollover", rollover_view),
        (generate, "Generate", generate_view),
        (export, "Export", export_view),
    ):
        with tab:
            _warn_if_unsaved_extraction(course_data)
            _gated(name, course_data, view.render, paths, course_data)
    with drafts:
        _guarded(drafts_view.render, paths)
    with metrics:
        _gated("Metrics", course_data, metrics_view.render, paths)
    with grading:
        _guarded(grading_view.render, paths)
    with settings:
        _guarded(settings_view.render, paths)
    background.render_tab_marks(
        session.TAB_GROUPS,
        session.GROUP_TAB_KEY,
        session.SUB_TAB_KEYS,
        inactive=NEEDS_COURSE_TABS if course_data is None else (),
    )

    _render_footer(paths)


def _sub_tabs(group: str):
    """A group's own row of tabs."""
    key = session.SUB_TAB_KEYS[group]
    return st.tabs(session.TAB_GROUPS[group], key=key, on_change=session.on_sub_tab_change, args=(key,))


ALL_COURSES = "All courses"


def _render_course_line(paths: ProjectPaths) -> None:
    """A way back to the projects list, then the open course. The button
    leads the line, bordered, where people look for "back": as a plain
    text "Switch course" at the far right it went unnoticed (UAT round 2).
    Leaving waits for a running job, whose result belongs to this course.
    The "Jump to…" dropdown ends the line."""
    busy = background.any_running()
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.button(
            ALL_COURSES,
            key="switch-course",
            icon=":material/arrow_back:",
            on_click=session.leave_project,
            disabled=busy,
            help="Wait for the current AI work to finish first." if busy else "Open or create another course.",
        )
        st.caption(f"Course project: {paths.root.name}")
        workflow_search.render()


def _resolve_project(argv: list[str]) -> ProjectPaths | None:
    paths = session.get_project()
    if paths is None:
        if session.is_switching_course():
            return None
        root = project_picker.project_from_argv(argv)
        if root is None:
            return None
    else:
        root = paths.root
    try:
        paths = open_project(root)
    except ChalkError as exc:
        st.error(exc.user_message)
        return None
    session.set_project(paths)
    return paths


def _load_course_or_warn(paths: ProjectPaths) -> CourseData | None:
    try:
        return load_course(paths)
    except ValueError:
        st.error(
            "Chalk couldn't read this course's saved details (course.json) — the file may have been "
            "edited by hand. Upload the syllabus again to replace it (the old file will be archived)."
        )
        return None


def _warn_if_unsaved_extraction(course_data: CourseData | None) -> None:
    """These tabs work from the saved course.json. A newly extracted
    syllabus isn't used until it's confirmed on the Review tab — say so,
    or the tab silently shows the previous course (teammate testing: a
    16-week upload showed the saved 10-week demo course's duration)."""
    pending = session.get_pending_extraction()
    if pending is None or course_data is None:
        return
    st.warning(
        f"You extracted {pending.course_data.course.title} but haven't saved it yet. This tab still "
        f"shows the saved course ({course_data.course.title}). Click **Confirm and save** on the "
        "Review tab to use the new syllabus, or **Discard** there to drop it."
    )


def _gated(tab: str, course_data: CourseData | None, render: Callable, *args) -> None:
    if course_data is None:
        render_needs_course(tab)
        return
    _guarded(render, *args)


def _guarded(render: Callable, *args) -> None:
    try:
        render(*args)
    except ChalkError as exc:
        st.error(exc.user_message)
    except Exception as exc:
        logger.exception("Unexpected error in %s", getattr(render, "__module__", render))
        st.error(
            f"Something unexpected went wrong ({type(exc).__name__}). Details were written to the "
            "terminal window running the app. Your files have not been changed."
        )


def _render_footer(paths: ProjectPaths) -> None:
    cost = summarize_events(read_events(paths.eval_log)).total_cost_usd
    st.divider()
    st.caption(f"Provider: {describe_provider(effective_env(paths.env))} · Project cost to date: ${cost:.4f}")
