"""Upload tab (PRD section 7.2): upload a syllabus, run extraction, and
resolve anything that needs the instructor before review — an ambiguous
schedule table (DECISIONS.md manual override) or a failed term/Week-1
consistency check (PRD section 6.1)."""

from __future__ import annotations

import dataclasses
import tempfile
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from chalk.errors import AmbiguousTableError, ChalkError
from chalk.extractors import log_consistency_override
from chalk.pipeline import extract_syllabus
from chalk.project import ProjectPaths
from ui import session
from ui.session import PendingExtraction, TableChoice


@dataclass(frozen=True)
class UploadOutcome:
    """Exactly one field is set: what the view should do next."""

    pending: PendingExtraction | None = None
    table_choice: TableChoice | None = None
    error: str | None = None


def save_upload(filename: str, data: bytes) -> Path:
    """Write an uploaded file to a private temp folder under its original
    name (extraction copies it into source/ once it parses)."""
    path = Path(tempfile.mkdtemp(prefix="chalk-upload-")) / Path(filename).name
    path.write_bytes(data)
    return path


def extract_upload(paths: ProjectPaths, upload_path: Path, table_index: int | None = None) -> UploadOutcome:
    try:
        course_data, consistency = extract_syllabus(paths, upload_path, schedule_table_index=table_index)
    except AmbiguousTableError as exc:
        if exc.candidates:
            return UploadOutcome(table_choice=TableChoice(upload_path, exc.candidates))
        return UploadOutcome(error=exc.user_message)
    except ChalkError as exc:
        return UploadOutcome(error=exc.user_message)
    return UploadOutcome(
        pending=PendingExtraction(course_data, consistency, acknowledged=consistency.passed)
    )


def render(paths: ProjectPaths) -> None:
    table_choice = session.get_table_choice()
    if table_choice is not None:
        _render_table_picker(paths, table_choice)
        return

    pending = session.get_pending_extraction()
    if pending is not None and not pending.acknowledged:
        _render_consistency_warning(paths, pending)
        return

    uploaded = st.file_uploader("Syllabus (.docx or .md)", type=["docx", "md"])
    if st.button("Extract course", type="primary", disabled=uploaded is None):
        with st.spinner("Reading the syllabus…"):
            outcome = extract_upload(paths, save_upload(uploaded.name, uploaded.getvalue()))
        _apply(outcome)

    if pending is not None:
        st.success(
            f"Extracted {pending.course_data.course.title}. Check it on the Review tab, "
            "then click Confirm and save."
        )


def _apply(outcome: UploadOutcome) -> None:
    if outcome.error:
        st.error(outcome.error)
        return
    session.set_table_choice(outcome.table_choice)
    if outcome.pending is not None:
        session.set_pending_extraction(outcome.pending)
        session.set_rollover_plan(None)
    st.rerun()


def _render_table_picker(paths: ProjectPaths, choice: TableChoice) -> None:
    st.warning("Multiple possible schedule tables were found. Choose the correct one below.")
    index = st.radio(
        "Schedule table",
        range(len(choice.candidates)),
        format_func=lambda i: f"Table {i + 1}: {choice.candidates[i]}",
    )
    use_col, cancel_col = st.columns(2)
    if use_col.button("Use this table", type="primary"):
        _apply(extract_upload(paths, choice.upload_path, index))
    if cancel_col.button("Cancel", key="cancel-table-choice"):
        session.set_table_choice(None)
        st.rerun()


def _render_consistency_warning(paths: ProjectPaths, pending: PendingExtraction) -> None:
    st.warning(
        "**⚠ Term and schedule don't match**  \n" + pending.consistency.detail.replace("\n", "  \n")
    )
    continue_col, cancel_col = st.columns(2)
    if continue_col.button("Continue anyway"):
        log_consistency_override(paths.eval_log, pending.consistency)
        session.set_pending_extraction(dataclasses.replace(pending, acknowledged=True))
        st.rerun()
    if cancel_col.button("Cancel", key="cancel-extraction"):
        session.set_pending_extraction(None)
        st.rerun()
