"""Small rendering helpers shared by every view."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from chalk.project import ProjectPaths

NEEDS_COURSE_MESSAGE = "Upload and extract a syllabus first — this tab needs a saved course.json."

_MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".html": "text/html",
    ".json": "application/json",
    ".zip": "application/zip",
}


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
