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
from chalk.models import CourseData
from chalk.pipeline import RolloverPlan
from chalk.project import ProjectPaths

PROJECT_ROOT_KEY = "chalk_project_root"
_SETUP_SKIPPED_KEY = "chalk_setup_skipped"
_PENDING_EXTRACTION_KEY = "chalk_pending_extraction"
_TABLE_CHOICE_KEY = "chalk_table_choice"
_ROLLOVER_PLAN_KEY = "chalk_rollover_plan"
_ROLLOVER_WRITTEN_KEY = "chalk_rollover_written"
_FLASH_KEY = "chalk_flash"


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
    instructor's pick (DECISIONS.md manual override)."""

    upload_path: Path
    candidates: list[str]


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


def setup_skipped() -> bool:
    return st.session_state.get(_SETUP_SKIPPED_KEY, False)


def skip_setup() -> None:
    st.session_state[_SETUP_SKIPPED_KEY] = True


# ---- Upload / Review ------------------------------------------------------------


def get_pending_extraction() -> PendingExtraction | None:
    return st.session_state.get(_PENDING_EXTRACTION_KEY)


def set_pending_extraction(pending: PendingExtraction | None) -> None:
    st.session_state[_PENDING_EXTRACTION_KEY] = pending


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


def set_rollover_written(paths: list[Path]) -> None:
    st.session_state[_ROLLOVER_WRITTEN_KEY] = paths


# ---- One-shot messages that survive a rerun -------------------------------------


def flash(message: str) -> None:
    st.session_state[_FLASH_KEY] = message


def pop_flash() -> str | None:
    return st.session_state.pop(_FLASH_KEY, None)
