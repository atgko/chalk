"""Typed accessors over st.session_state.

Every piece of UI state lives behind a function here rather than as a
string key scattered through the views (PLAN.md Risk #8), so the keys
can't drift and each view reads like plain Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from chalk.extractors.consistency import ConsistencyResult
from chalk.generation.engine import GeneratedDraft
from chalk.models import CourseData
from chalk.pipeline import PdfConversion, RolloverPlan
from chalk.project import ProjectPaths

PROJECT_ROOT_KEY = "chalk_project_root"
ACTIVE_TAB_KEY = "chalk_active_tab"
GENERATION_CONTENT_KEY = "chalk_generation_content_type"
_NEXT_TAB_KEY = "chalk_next_tab"
_SETUP_SKIPPED_KEY = "chalk_setup_skipped"
_PENDING_EXTRACTION_KEY = "chalk_pending_extraction"
_TABLE_CHOICE_KEY = "chalk_table_choice"
_ROLLOVER_PLAN_KEY = "chalk_rollover_plan"
_ROLLOVER_WRITTEN_KEY = "chalk_rollover_written"
_ROLLOVER_NOTE_KEY = "chalk_rollover_note"
_DRAFT_KEY = "chalk_draft"
_REGENERATE_KEY = "chalk_regenerate"
_FLASH_KEY = "chalk_flash"
_SWITCHING_KEY = "chalk_switching_course"
_PDF_TRIED_KEY = "chalk_pdf_methods_tried"


@dataclass(frozen=True)
class PendingExtraction:
    """An extracted course awaiting review. `acknowledged` is True once the
    instructor clicked "Continue anyway" past a failed consistency check
    (or immediately, if the check passed)."""

    course_data: CourseData
    consistency: ConsistencyResult
    acknowledged: bool


@dataclass(frozen=True)
class TableChoice:
    """An upload whose schedule table was ambiguous, awaiting the
    instructor's pick (DECISIONS.md manual override). For a PDF, the
    conversion is kept so the PDF isn't read (or paid for) twice."""

    upload_path: Path
    candidates: list[str]
    pdf_conversion: PdfConversion | None = None


@dataclass(frozen=True)
class StoredPlan:
    """A rollover preview plus the form inputs it was computed from, so a
    stale preview is never confirmed after the inputs change."""

    inputs: tuple
    plan: RolloverPlan


# ---- Project -----------------------------------------------------------------


def get_project() -> ProjectPaths | None:
    root = st.session_state.get(PROJECT_ROOT_KEY)
    return ProjectPaths(Path(root)) if root else None


def set_project(paths: ProjectPaths) -> None:
    st.session_state[PROJECT_ROOT_KEY] = str(paths.root)


def leave_project() -> None:
    """Back to the launch screen to pick another course. Everything kept
    for this course (drafts, a pending extraction, a rollover preview) is
    dropped, and the `--project` the app was started with is ignored from
    now on, or it would reopen the same course."""
    st.session_state.clear()
    st.session_state[_SWITCHING_KEY] = True


def is_switching_course() -> bool:
    return st.session_state.get(_SWITCHING_KEY, False)


def setup_skipped() -> bool:
    return st.session_state.get(_SETUP_SKIPPED_KEY, False)


def skip_setup() -> None:
    st.session_state[_SETUP_SKIPPED_KEY] = True


# ---- Upload / Review ------------------------------------------------------------


def get_pending_extraction() -> PendingExtraction | None:
    return st.session_state.get(_PENDING_EXTRACTION_KEY)


def set_pending_extraction(pending: PendingExtraction | None) -> None:
    st.session_state[_PENDING_EXTRACTION_KEY] = pending


def pdf_methods_tried(filename: str) -> frozenset[str]:
    """The ways ("local", "ai") this PDF has been read this session."""
    return frozenset(st.session_state.get(_PDF_TRIED_KEY, {}).get(filename, ()))


def record_pdf_method(filename: str, method: str) -> None:
    tried = st.session_state.get(_PDF_TRIED_KEY, {})
    st.session_state[_PDF_TRIED_KEY] = {**tried, filename: frozenset({*tried.get(filename, ()), method})}


def get_table_choice() -> TableChoice | None:
    return st.session_state.get(_TABLE_CHOICE_KEY)


def set_table_choice(choice: TableChoice | None) -> None:
    st.session_state[_TABLE_CHOICE_KEY] = choice


# ---- Rollover ------------------------------------------------------------------


def get_rollover_plan() -> StoredPlan | None:
    return st.session_state.get(_ROLLOVER_PLAN_KEY)


def set_rollover_plan(stored: StoredPlan | None) -> None:
    st.session_state[_ROLLOVER_PLAN_KEY] = stored


def get_rollover_written() -> list[Path]:
    return st.session_state.get(_ROLLOVER_WRITTEN_KEY, [])


def set_rollover_written(paths: list[Path], note: str | None = None) -> None:
    """The files the last rollover wrote, and a note about one it
    planned but couldn't write (chalk.pipeline.missing_pdf_note)."""
    st.session_state[_ROLLOVER_WRITTEN_KEY] = paths
    st.session_state[_ROLLOVER_NOTE_KEY] = note


def get_rollover_note() -> str | None:
    return st.session_state.get(_ROLLOVER_NOTE_KEY)


# ---- Generate ------------------------------------------------------------------


def get_draft() -> GeneratedDraft | None:
    return st.session_state.get(_DRAFT_KEY)


def set_draft(draft: GeneratedDraft | None) -> None:
    st.session_state[_DRAFT_KEY] = draft
    st.session_state[_REGENERATE_KEY] = False


def regenerate_requested() -> bool:
    return st.session_state.get(_REGENERATE_KEY, False)


def request_regenerate(requested: bool) -> None:
    st.session_state[_REGENERATE_KEY] = requested


def set_generation_content_type(content_type: str) -> None:
    """Preselect a Generate workflow before that tab's widgets render."""
    st.session_state[GENERATION_CONTENT_KEY] = content_type


# ---- Tabs ----------------------------------------------------------------------


# The tabs are grouped by what they're for (sponsor meeting, Oct 28): a
# group with several tabs shows them as a second row of tabs. A tab's own
# name ("Generate") is what the rest of the app goes by; ACTIVE_TAB_KEY
# holds the open one, and the two rows of tabs are set from it.
TAB_GROUPS: dict[str, tuple[str, ...]] = {
    "Build": ("Upload", "Review", "Rollover", "Generate", "Drafts", "Export"),
    "Grading Assistant": ("Grading Assistant",),
    "Settings": ("AI Provider", "Metrics"),
}
GROUP_TAB_KEY = "chalk_tab_group"
SUB_TAB_KEYS = {"Build": "chalk_build_tab", "Settings": "chalk_settings_tab"}


def go_to_tab(name: str) -> None:
    """Open tab `name` on the next run. The tabs widgets can't be changed
    once they have rendered in this run, so the shell applies the request
    before it draws the tabs (`apply_tab_request`)."""
    st.session_state[_NEXT_TAB_KEY] = name


def active_tab() -> str:
    return st.session_state.get(ACTIVE_TAB_KEY) or "Upload"


def group_of(tab: str) -> str:
    return next(group for group, tabs in TAB_GROUPS.items() if tab in tabs)


def apply_tab_request() -> None:
    """Open a requested tab, then set both rows of tabs to the open one."""
    requested = st.session_state.pop(_NEXT_TAB_KEY, None)
    if requested is not None:
        st.session_state[ACTIVE_TAB_KEY] = requested
    tab = active_tab()
    if not any(tab in tabs for tabs in TAB_GROUPS.values()):
        tab = "Upload"  # e.g. a session from before the tabs were grouped
    group = group_of(tab)
    st.session_state[ACTIVE_TAB_KEY] = tab
    st.session_state[GROUP_TAB_KEY] = group
    if group in SUB_TAB_KEYS:
        st.session_state[SUB_TAB_KEYS[group]] = tab


def on_group_change() -> None:
    """A group was clicked: open the tab it showed last (its first tab the
    first time)."""
    group = st.session_state[GROUP_TAB_KEY]
    tabs = TAB_GROUPS[group]
    last = st.session_state.get(SUB_TAB_KEYS.get(group, ""))
    st.session_state[ACTIVE_TAB_KEY] = last if last in tabs else tabs[0]


def on_sub_tab_change(key: str) -> None:
    """A tab in a group's second row was clicked."""
    st.session_state[ACTIVE_TAB_KEY] = st.session_state[key]


# ---- One-shot messages that survive a rerun -------------------------------------


def flash(message: str) -> None:
    st.session_state[_FLASH_KEY] = message


def pop_flash() -> str | None:
    return st.session_state.pop(_FLASH_KEY, None)
