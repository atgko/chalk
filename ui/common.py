"""Small rendering helpers shared by every view."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from chalk.generation.document_export import EXPORT_FORMATS, document_title, export_document
from chalk.project import ProjectPaths

FERPA_NOTICE = (
    "Course materials only — don't upload student work, grades, rosters, or any other "
    "student information (FERPA)."
)
KICKER = "Syllabus & course materials toolkit"
NEEDS_COURSE_MESSAGE = "Upload and extract a syllabus first — this tab needs a saved course.json."

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


def relative(path: Path, paths: ProjectPaths) -> str:
    return path.relative_to(paths.root).as_posix()


def download_button(path: Path, paths: ProjectPaths, *, key_prefix: str) -> None:
    """A download button for one project file, labeled by its project path."""
    label = relative(path, paths)
    st.download_button(
        f"Download {label}",
        data=path.read_bytes(),
        file_name=path.name,
        mime=_MIME_TYPES.get(path.suffix, "application/octet-stream"),
        key=f"{key_prefix}-{label}",
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
