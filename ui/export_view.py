"""Export tab (PRD section 7.2): every current output with a download
button, a copyable Canvas HTML block, and download-all-as-zip."""

from __future__ import annotations

import streamlit as st

from chalk.errors import ChalkError
from chalk.models import CourseData
from chalk.pipeline import export_outputs
from chalk.project import ProjectPaths, list_output_files, zip_outputs
from ui import common, session


def render(paths: ProjectPaths, course_data: CourseData) -> None:
    if st.button("Regenerate Canvas HTML and course brief"):
        try:
            export_outputs(paths, course_data)
        except ChalkError as exc:
            st.error(exc.user_message)
            return
        session.flash("Regenerated outputs/canvas.html and outputs/course-brief.md.")
        st.rerun()

    files = list_output_files(paths)
    if not files:
        st.info("No outputs yet. Save a course on the Review tab or run a rollover to create them.")
        return

    st.download_button(
        "Download all as zip",
        data=zip_outputs(paths),
        file_name=f"{paths.root.name}-outputs.zip",
        mime="application/zip",
        type="primary",
    )
    for path in files:
        common.download_button(path, paths, key_prefix="export")

    if paths.canvas_html.exists():
        st.markdown("#### Canvas HTML")
        st.caption("Use the copy button at the top right of the box, then paste into Canvas's HTML editor.")
        st.code(paths.canvas_html.read_text(encoding="utf-8"), language="html")
