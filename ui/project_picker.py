"""Launch screen: choose or create the course project to work on. The
app comes back here when the instructor clicks All courses.

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
from chalk.project import ProjectPaths, init_project, list_projects, open_project
from ui import folder_picker, session
from ui.common import render_header

DEFAULT_PARENT = Path.cwd() / "projects"
_FOLDER_KEY = "chalk_open_folder"
_PARENT_KEY = "chalk_create_parent"
# An open Browse… dialog: (field key, process). The page polls it.
_DIALOG_KEY = "chalk_folder_dialog"
# A folder picked in the dialog, applied to its field before the field
# renders on the next run: (field key, folder).
_CHOSEN_KEY = "chalk_folder_chosen"
_BROWSE_FAILED_KEY = "chalk_folder_dialog_failed"
# A Create that named an existing project: its folder, offered to open instead.
_EXISTING_KEY = "chalk_create_existing"
_DIALOG_POLL_SECONDS = 0.5


def project_from_argv(argv: list[str]) -> Path | None:
    """The `--project` argument passed after `streamlit run app.py --`."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", type=Path)
    args, _ = parser.parse_known_args(argv)
    return args.project


def render() -> None:
    _apply_chosen_folder()
    render_header(branding.PROJECT_NAME)
    st.write(
        "Keep your syllabus current from term to term and draft course materials from it. "
        "Everything stays in one course project folder on this computer."
    )
    open_col, create_col = st.columns(2)

    # Forms read the fields on click: typing doesn't rerun (and grey out)
    # the page, and Enter in a field submits.
    with open_col:
        st.subheader("Open a course project")
        _your_projects()
        with st.form("open-project", border=False):
            folder = _folder_field(
                "Project folder",
                _FOLDER_KEY,
                "Choose the course project folder",
                placeholder=str(DEFAULT_PARENT / "IS-6640-Fall-2027"),
            )
            if st.form_submit_button("Open project"):
                _open(folder.strip())

    with create_col:
        with st.form("create-project", border=False):
            st.subheader("Create a new one")
            st.session_state.setdefault(_PARENT_KEY, str(DEFAULT_PARENT))
            parent = _folder_field("Create it inside", _PARENT_KEY, "Choose where to create the project")
            name = st.text_input("Project name", placeholder="IS-6640-Fall-2027")
            if st.form_submit_button("Create project", type="primary"):
                _create(parent.strip(), name.strip())
        _offer_existing_project()

    _watch_dialog()
    if st.session_state.pop(_BROWSE_FAILED_KEY, False):
        st.warning("The folder window couldn't open. Type or paste the folder path instead.")

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


def _your_projects() -> None:
    """The projects in the default projects/ folder, most recently used
    first, so the usual case needs no typing or browsing."""
    projects = list_projects(DEFAULT_PARENT)
    if not projects:
        return
    with st.form("open-your-project", border=False):
        choice = st.selectbox("Your projects", projects, format_func=lambda paths: paths.root.name)
        if st.form_submit_button("Open"):
            _open(str(choice.root))
    st.caption("Or open a project folder from somewhere else:")


def _folder_field(label: str, key: str, dialog_title: str, **text_input_args) -> str:
    """A folder path field, with a Browse… button that opens the system
    folder dialog when this Python can show one."""
    if not folder_picker.is_available():
        return st.text_input(label, key=key, **text_input_args)
    field_col, browse_col = st.columns([5, 1], vertical_alignment="bottom")
    value = field_col.text_input(label, key=key, **text_input_args)
    browse_col.form_submit_button(
        "Browse…",
        key=f"{key}-browse",
        on_click=_browse_into,
        args=(key, dialog_title),
        disabled=_DIALOG_KEY in st.session_state,
    )
    return value


def _browse_into(key: str, dialog_title: str) -> None:
    """Button callback: opens the dialog and returns at once; the page
    then polls it (`_watch_dialog`)."""
    if _DIALOG_KEY in st.session_state:
        return
    current = st.session_state.get(key, "").strip()
    initial = current if current and Path(current).is_dir() else str(DEFAULT_PARENT)
    process = folder_picker.start(initial if Path(initial).is_dir() else "", dialog_title)
    if process is None:
        st.session_state[_BROWSE_FAILED_KEY] = True
        return
    st.session_state[_DIALOG_KEY] = (key, process)


@st.fragment(run_every=_DIALOG_POLL_SECONDS)
def _watch_dialog() -> None:
    """While a dialog is open: say where it is and offer Cancel. Once it
    closes: hand its folder to the field and rerun the page (a cancelled
    dialog leaves the field as it was)."""
    dialog = st.session_state.get(_DIALOG_KEY)
    if dialog is None:
        return
    key, process = dialog
    if not folder_picker.finished(process):
        st.info(
            "Choose a folder in the window that just opened, then click **Select Folder**. "
            "If you can't see it, it may be behind your browser: click its icon in the taskbar."
        )
        st.button("Cancel", key="folder-dialog-cancel", on_click=_cancel_dialog)
        return
    chosen = folder_picker.chosen_folder(process)
    del st.session_state[_DIALOG_KEY]
    if chosen:
        st.session_state[_CHOSEN_KEY] = (key, chosen)
    st.rerun()


def _cancel_dialog() -> None:
    dialog = st.session_state.pop(_DIALOG_KEY, None)
    if dialog is not None:
        folder_picker.cancel(dialog[1])


def _apply_chosen_folder() -> None:
    """Fill a field from the dialog. Runs before the fields render, since
    Streamlit only lets a widget's value change before it's drawn."""
    chosen = st.session_state.pop(_CHOSEN_KEY, None)
    if chosen is not None:
        key, folder = chosen
        st.session_state[key] = folder


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
    existing = ProjectPaths(Path(parent) / name)
    if existing.config_json.is_file():
        st.session_state[_EXISTING_KEY] = str(existing.root)
        return
    st.session_state.pop(_EXISTING_KEY, None)
    _enter(lambda: init_project(parent, name), f"Creating {name}…", f"Created project {name} in {parent}.")


def _offer_existing_project() -> None:
    """After Create named an existing project: open it, or pick another
    name. There's deliberately no overwrite, which would delete a course's
    files and their archived versions in one click."""
    existing = st.session_state.get(_EXISTING_KEY)
    if existing is None:
        return
    folder = Path(existing)
    st.warning(
        f"There's already a course project named {folder.name} in {folder.parent}. Open it, or "
        "choose another name. To start over, rename or delete that folder first."
    )
    open_col, other_col = st.columns(2)
    if open_col.button(f"Open {folder.name}", type="primary"):
        del st.session_state[_EXISTING_KEY]
        _open(existing)
    if other_col.button("Choose another name"):
        del st.session_state[_EXISTING_KEY]
        st.rerun()


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
