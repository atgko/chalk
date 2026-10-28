"""First-run setup (PRD section 7.1): shown when the project's .env is
missing or incomplete."""

from __future__ import annotations

import streamlit as st

from chalk import branding
from chalk.project import ProjectPaths
from ui import provider_form, session
from ui.common import render_header


def render(paths: ProjectPaths) -> None:
    render_header(f"Welcome to {branding.PROJECT_NAME}")
    message = session.pop_flash()  # e.g. "Created project …" from the launch screen
    if message:
        st.success(message)
    st.write(
        f"{branding.PROJECT_NAME} reads your syllabus, rolls it forward to a new term, and drafts "
        "quizzes, discussion prompts, and rubrics from it. Connect an AI model provider to "
        "get started. You only do this once: your key is saved securely in this computer's password "
        "store and used by all your courses."
    )
    saved = provider_form.render(paths, submit_label="Test connection and continue", key="setup")
    if saved:
        session.flash(saved)
        st.rerun()

    st.divider()
    st.caption(
        "Extraction, rollover, and export work without an AI provider. "
        "You can connect one later in the Settings tab."
    )
    if st.button("Skip for now"):
        session.skip_setup()
        st.rerun()
