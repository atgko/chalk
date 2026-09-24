"""Settings tab (DECISIONS.md, 7th tab): provider, model, and API key
only. Always available, regardless of project state."""

from __future__ import annotations

import streamlit as st

from chalk.config import describe_provider, read_env
from chalk.project import ProjectPaths
from ui import provider_form, session


def render(paths: ProjectPaths) -> None:
    st.caption(f"Current provider: {describe_provider(read_env(paths.env))}")
    if provider_form.render(paths, submit_label="Test connection and save", key="settings"):
        session.flash("Connected and saved.")
        st.rerun()
    st.divider()
    st.caption(
        f"Project folder: {paths.root}. Cost rates, archiving, and output formats are set in "
        "config.json in that folder."
    )
