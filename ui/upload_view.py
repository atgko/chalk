"""Upload tab (PRD section 7.2): upload a syllabus, run extraction, and
resolve anything that needs the instructor before review — an ambiguous
schedule table (DECISIONS.md manual override) or a failed term/Week-1
consistency check (PRD section 6.1).

A PDF syllabus is read into a Word file first, the way the instructor
chooses: on this computer (free, private) or with AI (handles unusual
layouts, costs a few cents). Either way they can download that Word file.

Extraction runs in the background, so switching tabs doesn't stop an AI
read of a PDF partway through (ui/background.py).
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
from chalk.progress import ProgressCallback, report, within
from chalk.project import ProjectPaths
from ui import background, common, session
from ui.session import PendingExtraction, TableChoice

# Share of the bar for an AI read of a PDF; extraction after it is quick.
_AI_READ_SHARE = 0.9
_FINISHING = 0.95

_PDF_METHOD_LABELS = {
    "local": "Read it on this computer",
    "ai": "Read it with AI",
}
_WORD_HINT = "save it as Word (.docx) from the original document and upload that"


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
    tried: frozenset[str] = frozenset(),
    on_progress: ProgressCallback | None = None,
) -> UploadOutcome:
    """Extract an uploaded syllabus, converting a PDF first (unless an
    earlier conversion is passed in). An AI read of a PDF fills the first
    90% of the progress bar; the rest is quick. `tried` is the ways this
    PDF was already read, so a failure suggests only the others."""
    try:
        reading_with_ai = pdf_conversion is None and is_pdf(upload_path.name) and pdf_method == "ai"
        if pdf_conversion is None and is_pdf(upload_path.name):
            pdf_conversion = convert_pdf_syllabus(
                paths, upload_path, method=pdf_method, on_progress=within(on_progress, 0.0, _AI_READ_SHARE)
            )
        report(on_progress, _FINISHING if reading_with_ai else None, "Finding the course details and schedule")
        course_data, consistency = extract_syllabus(
            paths, upload_path, schedule_table_index=table_index, pdf_conversion=pdf_conversion
        )
    except AmbiguousTableError as exc:
        if exc.candidates:
            return UploadOutcome(table_choice=TableChoice(upload_path, exc.candidates, pdf_conversion))
        return UploadOutcome(error=_with_pdf_hint(exc.user_message, upload_path, pdf_method, tried))
    except ChalkError as exc:
        return UploadOutcome(error=_with_pdf_hint(exc.user_message, upload_path, pdf_method, tried))
    return UploadOutcome(
        pending=PendingExtraction(course_data, consistency, acknowledged=consistency.passed),
        notice=_ai_cost_notice(pdf_conversion),
    )


def _with_pdf_hint(
    message: str, upload_path: Path, pdf_method: PdfReadMethod, tried: frozenset[str] = frozenset()
) -> str:
    """After a PDF read fails, suggest only what hasn't been tried on it
    (UAT of PR #18: an AI read that failed sent the professor to the
    local read, which had already failed)."""
    if not is_pdf(upload_path.name):
        return message
    untried = [method for method in PDF_READ_METHODS if method not in tried | {pdf_method}]
    if untried:
        return f"{message} Try **{_PDF_METHOD_LABELS[untried[0]]}** instead, or {_WORD_HINT}."
    return f"{message} Chalk couldn't read this PDF either way. To fix it, {_WORD_HINT}."


def _ai_cost_notice(conversion: PdfConversion | None) -> str | None:
    if conversion is None or conversion.method != "ai":
        return None
    return f"Read {conversion.pdf_name} with AI. Cost: {format_cost(conversion.cost_usd)}."


_JOB = "extract"
_TAB = "Upload"
# The last failed read's message, shown until the next read starts or one
# succeeds, so a failure never lingers after a read that worked (UAT round 2).
_ERROR_KEY = "chalk_upload_error"


def render(paths: ProjectPaths) -> None:
    finished = background.take_finished(_JOB)
    if finished is not None:
        _apply(finished.result(), elsewhere=session.active_tab() != _TAB)
    background.pop_error(_TAB)  # a failure's message is kept in _ERROR_KEY instead
    if background.is_running(_JOB):
        background.render_progress(_JOB)
        return
    error = st.session_state.get(_ERROR_KEY)
    if error:
        st.error(error)

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
        label = f"Reading {uploaded.name}"
        upload_path = save_upload(uploaded.name, uploaded.getvalue())
        tried = session.pdf_methods_tried(uploaded.name)
        if is_pdf(uploaded.name):
            session.record_pdf_method(uploaded.name, pdf_method)
        st.session_state.pop(_ERROR_KEY, None)
        background.start(
            _JOB, label, extract_upload, paths, upload_path, pdf_method=pdf_method, tried=tried, tab=_TAB
        )
        st.rerun()

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
        ai_caption = "Set up an AI provider under Settings → AI Provider to use this."
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


def _apply(outcome: UploadOutcome, *, elsewhere: bool = False) -> None:
    """Act on an extraction. `elsewhere` means the instructor moved to
    another tab while it ran: leave them there and say what happened."""
    if outcome.error:
        st.session_state[_ERROR_KEY] = outcome.error
        if elsewhere:
            background.finished_elsewhere(_TAB, outcome.error, failed=True)
        st.rerun()
    st.session_state.pop(_ERROR_KEY, None)
    session.set_table_choice(outcome.table_choice)
    messages = [outcome.notice] if outcome.notice else []
    if outcome.pending is not None:
        session.set_pending_extraction(outcome.pending)
        session.set_rollover_plan(None)
        if outcome.pending.acknowledged:  # otherwise the term warning stays on Upload
            if elsewhere:
                messages.append(f"Extracted {outcome.pending.course_data.course.title}. Check it on the Review tab.")
            else:
                session.go_to_tab("Review")
    if elsewhere and (outcome.table_choice or (outcome.pending and not outcome.pending.acknowledged)):
        messages.append("Your syllabus is read. Chalk needs a decision from you on the Upload tab.")
    if messages and elsewhere:
        background.finished_elsewhere(_TAB, " ".join(messages))
    elif messages:
        session.flash(" ".join(messages))
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
        st.session_state.pop(_ERROR_KEY, None)
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
        session.go_to_tab("Review")
        st.rerun()
    if cancel_col.button("Cancel", key="cancel-extraction"):
        session.set_pending_extraction(None)
        st.rerun()
