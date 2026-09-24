"""Launch screen: choose or create the one course project this app
instance works on (DECISIONS.md — no in-app project switcher).

Skipped entirely when the app is started with
`streamlit run app.py -- --project <folder>`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import streamlit as st

from chalk import branding
from chalk.errors import ChalkError
from chalk.project import init_project, open_project
from ui import session

DEFAULT_PARENT = Path.cwd() / "projects"


def project_from_argv(argv: list[str]) -> Path | None:
    """The `--project` argument passed after `streamlit run app.py --`."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", type=Path)
    args, _ = parser.parse_known_args(argv)
    return args.project


def render() -> None:
    st.title(branding.PROJECT_NAME)
    st.write(
        "Keep your syllabus current from term to term and draft course materials from it. "
        "Everything stays in one course project folder on this computer."
    )
    open_col, create_col = st.columns(2)

    with open_col:
        st.subheader("Open a course project")
        folder = st.text_input("Project folder", placeholder=str(DEFAULT_PARENT / "IS-6640-Fall-2027"))
        if st.button("Open project", disabled=not folder.strip()):
            _enter(lambda: open_project(folder.strip()))

    with create_col:
        st.subheader("Create a new one")
        parent = st.text_input("Create it inside", value=str(DEFAULT_PARENT))
        name = st.text_input("Project name", placeholder="IS-6640-Fall-2027")
        if st.button("Create project", type="primary", disabled=not name.strip()):
            _enter(lambda: init_project(parent.strip(), name))


def _enter(get_paths) -> None:
    try:
        paths = get_paths()
    except ChalkError as exc:
        st.error(exc.user_message)
        return
    session.set_project(paths)
    st.rerun()
