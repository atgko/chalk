"""First-run setup (PRD section 7.1): shown when the project's .env is
missing or incomplete."""

from __future__ import annotations

import streamlit as st

from chalk import branding
from chalk.project import ProjectPaths
from ui import provider_form, session


def render(paths: ProjectPaths) -> None:
    st.title(f"Welcome to {branding.PROJECT_NAME}")
    st.write(
        f"{branding.PROJECT_NAME} reads your syllabus, rolls it forward to a new term, and drafts "
        "quizzes, discussion prompts, and rubrics from it. Connect an AI model provider to "
        "get started — your key is saved only in this project's .env file."
    )
    if provider_form.render(paths, submit_label="Test connection and continue", key="setup"):
        st.rerun()

    st.divider()
    st.caption(
        "Extraction, rollover, and export work without an AI provider. "
        "You can connect one later in the Settings tab."
    )
    if st.button("Skip for now"):
        session.skip_setup()
        st.rerun()
