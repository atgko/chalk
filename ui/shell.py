"""App shell: project resolution, first-run setup, the seven tabs, tab
gating, and the provider/cost footer (PRD section 7, DECISIONS.md).

Every tab renders inside `_guarded`, so no traceback ever reaches the
screen: ChalkErrors show their plain-English message, anything
unexpected shows a short notice and is logged to the terminal.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

import streamlit as st
from dotenv import load_dotenv

from chalk import branding
from chalk.config import describe_provider, env_is_configured, read_env
from chalk.errors import ChalkError
from chalk.metrics import read_events, summarize_events
from chalk.models import CourseData
from chalk.project import ProjectPaths, load_course, open_project
from ui import (
    export_view,
    generate_view,
    metrics_view,
    project_picker,
    review_view,
    rollover_view,
    session,
    settings_view,
    setup_view,
    upload_view,
)
from ui.common import NEEDS_COURSE_MESSAGE, render_header

TAB_NAMES = ("Upload", "Review", "Rollover", "Generate", "Export", "Metrics", "Settings")

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    st.set_page_config(page_title=branding.PROJECT_NAME, page_icon="📘", layout="wide")

    paths = _resolve_project(sys.argv[1:] if argv is None else argv)
    if paths is None:
        project_picker.render()
        return

    if paths.env.exists():
        load_dotenv(paths.env, override=True)
    if not env_is_configured(paths.env) and not session.setup_skipped():
        setup_view.render(paths)
        return

    render_header(branding.PROJECT_NAME)
    st.caption(f"Course project: {paths.root.name}")
    message = session.pop_flash()
    if message:
        st.success(message)

    course_data = _load_course_or_warn(paths)
    upload, review, rollover, generate, export, metrics, settings = st.tabs(TAB_NAMES)
    with upload:
        _guarded(upload_view.render, paths)
    with review:
        _guarded(review_view.render, paths, course_data)
    for tab, view in ((rollover, rollover_view), (generate, generate_view), (export, export_view)):
        with tab:
            _gated(course_data, view.render, paths, course_data)
    with metrics:
        _gated(course_data, metrics_view.render, paths)
    with settings:
        _guarded(settings_view.render, paths)

    _render_footer(paths)


def _resolve_project(argv: list[str]) -> ProjectPaths | None:
    paths = session.get_project()
    if paths is None:
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
            "course.json couldn't be read — it may have been edited by hand. "
            "Fix it, or upload and extract the syllabus again (the old file will be archived)."
        )
        return None


def _gated(course_data: CourseData | None, render: Callable, *args) -> None:
    if course_data is None:
        st.info(NEEDS_COURSE_MESSAGE)
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
    st.caption(f"Provider: {describe_provider(read_env(paths.env))} · Project cost to date: ${cost:.4f}")
