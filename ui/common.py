"""Small rendering helpers shared by every view."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from chalk.generation.document_export import EXPORT_FORMATS, document_title, export_document
from chalk.project import ProjectPaths
from ui import session

FERPA_NOTICE = (
    "Course materials only — don't upload student work, grades, rosters, or any other "
    "student information (FERPA)."
)
KICKER = "Syllabus & course materials toolkit"
NEEDS_COURSE_MESSAGE = (
    "Start by uploading your syllabus. Chalk reads its schedule and course details, and this "
    "tab works from them."
)

_MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".html": "text/html",
    ".json": "application/json",
    ".zip": "application/zip",
}


def render_header(title: str) -> None:
    """Page heading: a short Utah Red kicker line over a serif title, as on
    the reference design. The kicker names what the tool is, not an
    institution, so it never reads as an official University product."""
    st.markdown(f":red[**{KICKER}**]")
    st.title(title)


def render_needs_course(tab: str) -> None:
    """What a tab shows before any syllabus is saved: why it's empty and
    a button to the Upload tab (UAT of PR #18: the old message named
    course.json, which means nothing to a professor)."""
    st.info(NEEDS_COURSE_MESSAGE, icon="📄")
    st.button("Go to Upload", key=f"needs-course-{tab}", on_click=session.go_to_tab, args=("Upload",))


def relative(path: Path, paths: ProjectPaths) -> str:
    """`path` as shown to the instructor: relative to the project folder."""
    return path.relative_to(paths.root).as_posix()


def download_button(path: Path, paths: ProjectPaths, *, key_prefix: str, label: str | None = None) -> None:
    """A download button for one project file, labeled `label` or else by
    its project path."""
    project_path = relative(path, paths)
    st.download_button(
        label or f"Download {project_path}",
        data=path.read_bytes(),
        file_name=path.name,
        mime=_MIME_TYPES.get(path.suffix, "application/octet-stream"),
        key=f"{key_prefix}-{project_path}",
    )


def export_buttons(text: str, *, content_type: str, subject: str, base_name: str, key: str) -> None:
    """File-type choice and download for a generated document, in the
    assignment creator's Word/PDF layout (or the markdown as saved)."""
    file_format = st.selectbox("File type", EXPORT_FORMATS, key=f"{key}-format")
    data, extension, mime = export_document(
        text, file_format, content_type=content_type, title=document_title(content_type, subject)
    )
    st.download_button(
        f"Download {file_format}",
        data=data,
        file_name=f"{base_name}.{extension}",
        mime=mime,
        key=f"{key}-download",
    )


# Where each Build tab sits in the usual path through Chalk, shown at the
# top of the tab (Nov 9 UAT: "direct them" so the workflow is obvious).
WORKFLOW_STEPS = {
    "Upload": "**Step 1 of 4 · Upload.** Choose your current syllabus. Chalk reads its schedule and course details.",
    "Review": "**Step 2 of 4 · Review.** Check what Chalk read, fix anything blank or wrong, then click Confirm and save.",
    "Rollover": "**Step 3 of 4 · Rollover.** Pick the new term, preview every date change, then confirm.",
    "Export": "**Step 4 of 4 · Export.** Download the new syllabus and the Canvas page.",
    "Generate": "**Optional · Generate.** Draft quizzes, assignments, and more from your own source materials.",
    "Drafts": "**Optional · Drafts.** Everything you saved from Generate.",
}


def render_step(tab: str) -> None:
    """The tab's place in the workflow, as a one-line caption."""
    if tab in WORKFLOW_STEPS:
        st.caption(WORKFLOW_STEPS[tab])
