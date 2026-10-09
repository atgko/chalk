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
from ui import folder_picker, session
from ui.common import render_header

DEFAULT_PARENT = Path.cwd() / "projects"
_FOLDER_KEY = "chalk_open_folder"
_PARENT_KEY = "chalk_create_parent"


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
        folder = _folder_field(
            "Project folder",
            _FOLDER_KEY,
            "Choose the course project folder",
            placeholder=str(DEFAULT_PARENT / "IS-6640-Fall-2027"),
        )
        if st.form_submit_button("Open project"):
            _open(folder.strip())

    with create_col, st.form("create-project", border=False):
        st.subheader("Create a new one")
        st.session_state.setdefault(_PARENT_KEY, str(DEFAULT_PARENT))
        parent = _folder_field("Create it inside", _PARENT_KEY, "Choose where to create the project")
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


def _folder_field(label: str, key: str, dialog_title: str, **text_input_args) -> str:
    """A folder path field, with a Browse… button that opens the system
    folder dialog when this Python can show one."""
    if not folder_picker.is_available():
        return st.text_input(label, key=key, **text_input_args)
    field_col, browse_col = st.columns([5, 1], vertical_alignment="bottom")
    value = field_col.text_input(label, key=key, **text_input_args)
    browse_col.form_submit_button("Browse…", key=f"{key}-browse", on_click=_browse_into, args=(key, dialog_title))
    return value


def _browse_into(key: str, dialog_title: str) -> None:
    """Button callback: runs before the page reruns, so it may set the
    field's value. A cancelled dialog leaves the field as it was."""
    current = st.session_state.get(key, "").strip()
    initial = current if current and Path(current).is_dir() else str(DEFAULT_PARENT)
    chosen = folder_picker.pick_folder(initial if Path(initial).is_dir() else "", dialog_title)
    if chosen:
        st.session_state[key] = chosen


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
