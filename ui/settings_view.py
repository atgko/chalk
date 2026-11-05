"""Settings → AI Provider tab (DECISIONS.md): provider, model, and API
key only. Always available, regardless of project state."""

from __future__ import annotations

import streamlit as st

from chalk.config import describe_provider, effective_env
from chalk.project import ProjectPaths
from ui import provider_form, session


def render(paths: ProjectPaths) -> None:
    st.caption(f"Current provider: {describe_provider(effective_env(paths.env))}")
    st.caption(
        "Your key is saved once on this computer (in its password store) and used by all your "
        "courses. Saving here replaces it for all of them."
    )
    saved = provider_form.render(paths, submit_label="Test connection and save", key="settings")
    if saved:
        session.flash(saved)
        st.rerun()
    st.divider()
    st.caption(
        f"Project folder: {paths.root}. Cost rates, archiving, and output formats are set in "
        "config.json in that folder."
    )
