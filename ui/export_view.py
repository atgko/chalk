"""Export tab (PRD section 7.2): every current output with a download
button, the Canvas syllabus page (how to paste it in, a preview of how it
will look, and a copyable HTML block), and download-all-as-zip."""

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
        _render_canvas_page(paths.canvas_html.read_text(encoding="utf-8"))


# Where the professor pastes the page, step by step (UAT round 2: staff
# weren't sure what to do with the HTML).
CANVAS_STEPS = """1. In your Canvas course, click **Syllabus** in the menu on the left.
2. Click **Edit** at the top right of the Course Syllabus page.
3. In the editor's menu, click **View**, then **HTML Editor**.
4. Select everything in the HTML editor (Ctrl+A, or Cmd+A on a Mac) and delete it.
5. Click the copy button at the top right of the HTML box below, then paste into the HTML editor (Ctrl+V, or Cmd+V).
6. Click **Update Syllabus**. Then fill in the parts marked "Insert…" (email, office hours, TAs)."""

# Canvas pages are white, whatever Chalk's theme, so the preview is too.
_PREVIEW_FRAME = (
    '<div style="background: #ffffff; color: #2d3b45; padding: 16px; border-radius: 8px; '
    "font-family: Lato, 'Helvetica Neue', Arial, sans-serif;\">{page}</div>"
)


def _render_canvas_page(page_html: str) -> None:
    st.markdown("#### Canvas syllabus page")
    st.caption(
        "Your Canvas syllabus page, filled in from the course: the banner, instructor details, "
        "learning objectives, grading, the schedule, and the standard help and accessibility sections."
    )
    st.markdown("**How to put it on Canvas**")
    st.markdown(CANVAS_STEPS)
    with st.expander("Preview: how it will look in Canvas", expanded=True):
        st.html(_PREVIEW_FRAME.format(page=page_html))
    st.markdown("**HTML to paste**")
    st.code(page_html, language="html")
