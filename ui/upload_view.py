"""Upload tab (PRD section 7.2): upload a syllabus, run extraction, and
resolve anything that needs the instructor before review — an ambiguous
schedule table (DECISIONS.md manual override) or a failed term/Week-1
consistency check (PRD section 6.1).

A PDF syllabus is read into a Word file first, the way the instructor
chooses: on this computer (free, private) or with AI (handles unusual
layouts, costs a few cents). Either way they can download that Word file.
"""

from __future__ import annotations

import dataclasses
import tempfile
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from chalk.config import describe_provider, env_is_configured
from chalk.costs import format_cost
from chalk.errors import AmbiguousTableError, ChalkError
from chalk.extractors import log_consistency_override
from chalk.generation.engine import current_env
from chalk.pdf_import import PDF_READ_METHODS, PdfReadMethod, is_converted_from_pdf
from chalk.pipeline import (
    PdfConversion,
    convert_pdf_syllabus,
    estimate_ai_reading_cost_per_page,
    extract_syllabus,
)
from chalk.project import ProjectPaths
from ui import common, session
from ui.session import PendingExtraction, TableChoice

_PDF_METHOD_LABELS = {
    "local": "Read it on this computer",
    "ai": "Read it with AI",
}
_LOCAL_HINT = (
    " You can also try **Read it with AI**, or save the PDF as Word (.docx) and upload that."
)


@dataclass(frozen=True)
class UploadOutcome:
    """Exactly one of `pending`, `table_choice`, `error` is set: what the
    view should do next. `notice` is an optional extra message (e.g. what
    an AI read of a PDF cost)."""

    pending: PendingExtraction | None = None
    table_choice: TableChoice | None = None
    error: str | None = None
    notice: str | None = None


def save_upload(filename: str, data: bytes) -> Path:
    """Write an uploaded file to a private temp folder under its original
    name (extraction copies it into source/ once it parses)."""
    path = Path(tempfile.mkdtemp(prefix="chalk-upload-")) / Path(filename).name
    path.write_bytes(data)
    return path


def is_pdf(filename: str) -> bool:
    return Path(filename).suffix.lower() == ".pdf"


def extract_upload(
    paths: ProjectPaths,
    upload_path: Path,
    table_index: int | None = None,
    *,
    pdf_method: PdfReadMethod = "local",
    pdf_conversion: PdfConversion | None = None,
) -> UploadOutcome:
    """Extract an uploaded syllabus, converting a PDF first (unless an
    earlier conversion is passed in)."""
    try:
        if pdf_conversion is None and is_pdf(upload_path.name):
            pdf_conversion = convert_pdf_syllabus(paths, upload_path, method=pdf_method)
        course_data, consistency = extract_syllabus(
            paths, upload_path, schedule_table_index=table_index, pdf_conversion=pdf_conversion
        )
    except AmbiguousTableError as exc:
        if exc.candidates:
            return UploadOutcome(table_choice=TableChoice(upload_path, exc.candidates, pdf_conversion))
        return UploadOutcome(error=_with_pdf_hint(exc.user_message, upload_path, pdf_method))
    except ChalkError as exc:
        return UploadOutcome(error=_with_pdf_hint(exc.user_message, upload_path, pdf_method))
    return UploadOutcome(
        pending=PendingExtraction(course_data, consistency, acknowledged=consistency.passed),
        notice=_ai_cost_notice(pdf_conversion),
    )


def _with_pdf_hint(message: str, upload_path: Path, pdf_method: PdfReadMethod) -> str:
    """After a PDF read on this computer fails, point at the other options."""
    if is_pdf(upload_path.name) and pdf_method == "local":
        return message + _LOCAL_HINT
    return message


def _ai_cost_notice(conversion: PdfConversion | None) -> str | None:
    if conversion is None or conversion.method != "ai":
        return None
    return f"Read {conversion.pdf_name} with AI. Cost: {format_cost(conversion.cost_usd)}."


def render(paths: ProjectPaths) -> None:
    table_choice = session.get_table_choice()
    if table_choice is not None:
        _render_table_picker(paths, table_choice)
        return

    pending = session.get_pending_extraction()
    if pending is not None and not pending.acknowledged:
        _render_consistency_warning(paths, pending)
        return

    uploaded = st.file_uploader("Syllabus (.docx, .md, or .pdf)", type=["docx", "md", "pdf"])
    st.caption(common.FERPA_NOTICE)
    pdf_method: PdfReadMethod = "local"
    can_extract = uploaded is not None
    if uploaded is not None and is_pdf(uploaded.name):
        pdf_method = _pdf_method_choice(paths)
        can_extract = pdf_method == "local" or env_is_configured(paths.env)

    if st.button("Extract course", type="primary", disabled=not can_extract):
        spinner = "Reading the PDF — this can take a minute…" if is_pdf(uploaded.name) else "Reading the syllabus…"
        with st.spinner(spinner):
            outcome = extract_upload(paths, save_upload(uploaded.name, uploaded.getvalue()), pdf_method=pdf_method)
        _apply(outcome)

    if pending is not None:
        st.success(
            f"Extracted {pending.course_data.course.title}. Check it on the Review tab, "
            "then click Confirm and save."
        )
        _render_converted_download(paths, pending)


def _pdf_method_choice(paths: ProjectPaths) -> PdfReadMethod:
    configured = env_is_configured(paths.env)
    if configured:
        per_page = estimate_ai_reading_cost_per_page(paths)
        cost = "cost unknown for this model" if per_page is None else f"about ${per_page:.2f} per page"
        ai_caption = (
            f"For unusual layouts. Sends the syllabus text to {describe_provider(current_env())}; {cost}."
        )
    else:
        ai_caption = "Set up an AI provider on the Settings tab to use this."
    method = st.radio(
        "How should Chalk read this PDF?",
        PDF_READ_METHODS,
        format_func=_PDF_METHOD_LABELS.get,
        captions=["Free and private — nothing leaves this computer. Works for most syllabi.", ai_caption],
        key="pdf-method",
    )
    st.caption(
        "Chalk turns the PDF into a Word file and works from that, so a rollover gives you an "
        "editable .docx. Scanned PDFs (images of pages) can't be read."
    )
    return method


def _render_converted_download(paths: ProjectPaths, pending: PendingExtraction) -> None:
    source = paths.root / pending.course_data.course.source_file
    if is_converted_from_pdf(source.name) and source.is_file():
        st.caption("Chalk made this Word file from your PDF — it's what rollover will update.")
        common.download_button(source, paths, key_prefix="converted-pdf")


def _apply(outcome: UploadOutcome) -> None:
    if outcome.error:
        st.error(outcome.error)
        return
    session.set_table_choice(outcome.table_choice)
    if outcome.pending is not None:
        session.set_pending_extraction(outcome.pending)
        session.set_rollover_plan(None)
    if outcome.notice:
        session.flash(outcome.notice)
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
        _apply(extract_upload(paths, choice.upload_path, index, pdf_conversion=choice.pdf_conversion))
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
