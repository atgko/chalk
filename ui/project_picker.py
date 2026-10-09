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
from chalk.demo import open_demo_project
from chalk.errors import ChalkError
from chalk.project import init_project, open_project
from ui import session
from ui.common import render_header

DEFAULT_PARENT = Path.cwd() / "projects"


def project_from_argv(argv: list[str]) -> Path | None:
    """The `--project` argument passed after `streamlit run app.py --`."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", type=Path)
    args, _ = parser.parse_known_args(argv)
    return args.project


def render() -> None:
    render_header(branding.PROJECT_NAME)
    st.write(
        "Keep your syllabus current from term to term and draft course materials from it. "
        "Everything stays in one course project folder on this computer."
    )
    open_col, create_col = st.columns(2)

    # Forms read the fields on click: typing doesn't rerun (and grey out)
    # the page, and Enter in a field submits.
    with open_col, st.form("open-project", border=False):
        st.subheader("Open a course project")
        folder = st.text_input("Project folder", placeholder=str(DEFAULT_PARENT / "IS-6640-Fall-2027"))
        if st.form_submit_button("Open project"):
            _open(folder.strip())

    with create_col, st.form("create-project", border=False):
        st.subheader("Create a new one")
        parent = st.text_input("Create it inside", value=str(DEFAULT_PARENT))
        name = st.text_input("Project name", placeholder="IS-6640-Fall-2027")
        if st.form_submit_button("Create project", type="primary"):
            _create(parent.strip(), name.strip())

    st.divider()
    st.subheader("Just looking?")
    st.write(
        "Open a demo course with a sample syllabus already loaded. Its `try-these` folder has "
        "more sample files to upload."
    )
    demo_col, reset_col = st.columns(2)
    if demo_col.button("Open the demo course"):
        _enter(lambda: open_demo_project(DEFAULT_PARENT), "Opening the demo course…", "Opened the demo course.")
    if reset_col.button("Reset the demo course", help="Rebuild it from scratch. Keeps your saved AI key."):
        _enter(
            lambda: open_demo_project(DEFAULT_PARENT, reset=True),
            "Rebuilding the demo course…",
            "Reset the demo course.",
        )


def _open(folder: str) -> None:
    if not folder:
        st.warning("Enter the project folder, then click Open project.")
        return
    name = Path(folder).name
    _enter(lambda: open_project(folder), f"Opening {name}…", f"Opened project {name}.")


def _create(parent: str, name: str) -> None:
    if not name:
        st.warning("Enter a project name, then click Create project.")
        return
    _enter(lambda: init_project(parent, name), f"Creating {name}…", f"Created project {name} in {parent}.")


def _enter(get_paths, working: str, done: str) -> None:
    """Run `get_paths` under a status spinner, then enter the project with
    `done` shown on the next screen."""
    try:
        with st.spinner(working):
            paths = get_paths()
    except ChalkError as exc:
        st.error(exc.user_message)
        return
    session.set_project(paths)
    session.flash(done)
    st.rerun()
