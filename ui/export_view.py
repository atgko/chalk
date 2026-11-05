"""Export tab (PRD section 7.2): every current output, grouped by what it
is and named plainly, plus download-all-as-zip; then the Canvas syllabus
page (how to paste it in, a preview, and a copyable HTML block)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from chalk.errors import ChalkError
from chalk.generation.specs import SPECS
from chalk.models import CourseData
from chalk.pipeline import export_outputs
from chalk.project import ProjectPaths, list_output_files, zip_outputs
from ui import common, session

_FORMAT_NAMES = {".docx": "Word", ".pdf": "PDF", ".md": "Markdown"}
_MATERIAL_FOLDERS = tuple(spec.output_subdir for spec in SPECS.values())
_SECTION_NOTES = {
    "Syllabus": "The syllabus as Chalk last wrote it, from Confirm rollover.",
    "Course materials": "Drafts saved from Generate, as Markdown. For Word or PDF, open one on the Drafts tab.",
    "Canvas and course brief": (
        "Rebuilt whenever you save the course or roll it over. The course brief is the one-page "
        "summary Chalk gives the AI when it drafts course materials."
    ),
    "Other files": "Files in the outputs folder that Chalk didn't make.",
}
_BUTTONS_PER_ROW = 3


def render(paths: ProjectPaths, course_data: CourseData) -> None:
    files = list_output_files(paths)
    if not files:
        st.info("No outputs yet. Save a course on the Review tab or run a rollover to create them.")
    else:
        st.download_button(
            "Download everything (.zip)",
            data=zip_outputs(paths),
            file_name=f"{paths.root.name}-outputs.zip",
            mime="application/zip",
            type="primary",
        )
        for title, items in output_sections(files, paths):
            _render_section(paths, title, items)

    if paths.canvas_html.exists():
        _render_canvas_page(paths.canvas_html.read_text(encoding="utf-8"))
    _render_rebuild(paths, course_data)


def output_sections(files: list[Path], paths: ProjectPaths) -> list[tuple[str, list[tuple[str, Path]]]]:
    """The output files as (section title, [(button label, path)]), in the
    order the tab shows them, leaving out empty sections."""
    sections: dict[str, list[tuple[str, Path]]] = {title: [] for title in _SECTION_NOTES}
    for path in files:
        title, label = _describe(path, paths)
        sections[title].append((label, path))
    sections["Syllabus"].sort(key=lambda item: list(_FORMAT_NAMES).index(item[1].suffix))
    sections["Canvas and course brief"].sort(key=lambda item: item[1] != paths.canvas_html)
    return [(title, items) for title, items in sections.items() if items]


def _describe(path: Path, paths: ProjectPaths) -> tuple[str, str]:
    if path.parent == paths.outputs_dir and path.stem == "syllabus" and path.suffix in _FORMAT_NAMES:
        return "Syllabus", f"Syllabus ({_FORMAT_NAMES[path.suffix]})"
    if path == paths.canvas_html:
        return "Canvas and course brief", "Canvas syllabus page (HTML)"
    if path == paths.course_brief:
        return "Canvas and course brief", "Course brief"
    if path.parent.parent == paths.outputs_dir and path.parent.name in _MATERIAL_FOLDERS and path.suffix == ".md":
        name = path.stem.replace("-", " ")
        return "Course materials", name[:1].upper() + name[1:]
    return "Other files", common.relative(path, paths).removeprefix("outputs/")


def _render_section(paths: ProjectPaths, title: str, items: list[tuple[str, Path]]) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(_SECTION_NOTES[title])
        for start in range(0, len(items), _BUTTONS_PER_ROW):
            columns = st.columns(_BUTTONS_PER_ROW)
            for column, (label, path) in zip(columns, items[start : start + _BUTTONS_PER_ROW], strict=False):
                with column:
                    common.download_button(path, paths, key_prefix="export", label=label)


def _render_rebuild(paths: ProjectPaths, course_data: CourseData) -> None:
    """Rarely needed (F-03): Chalk rebuilds both on save and rollover."""
    with st.expander("Canvas page or course brief out of date?"):
        st.caption(
            "Chalk rebuilds them every time you save the course or roll it over. Rebuild them here "
            "only if they don't match the course, for example after editing course.json by hand."
        )
        if st.button("Rebuild the Canvas page and course brief"):
            try:
                export_outputs(paths, course_data)
            except ChalkError as exc:
                st.error(exc.user_message)
                return
            session.flash("Rebuilt the Canvas syllabus page and the course brief from the saved course.")
            st.rerun()


# Where the professor pastes the page, step by step (UAT round 2: staff
# weren't sure what to do with the HTML).
CANVAS_STEPS = """1. In your Canvas course, click **Syllabus** in the menu on the left.
2. Click **Edit** at the top right of the Course Syllabus page.
3. In the editor's menu, click **View**, then **HTML Editor**.
4. Select everything in the HTML editor (Ctrl+A, or Cmd+A on a Mac) and delete it.
5. Click the copy button at the top right of the HTML box below, then paste into the HTML editor (Ctrl+V, or Cmd+V).
6. Click **Update Syllabus**. Then fill in the parts marked "Insert…" (email, office hours, TAs)."""

# Canvas pages are white, whatever Chalk's theme, so the preview is too.
# The page itself carries no banner or section-bar styling: on Canvas the
# DesignPLUS theme draws them, so the preview stands in for that theme,
# scoped to .kl_emta so it can't touch the rest of the app. Not selectable,
# so it can't be copied in place of the HTML (a pasted preview brings
# Streamlit's own markup with it).
_PREVIEW_FRAME = (
    "<style>"
    ".kl_emta #kl_banner h2 {{ background: #be0000; color: #ffffff; padding: 12px 16px; border-radius: 6px; "
    "font-weight: normal; }}"
    ".kl_emta h3 {{ background: #c7cdd1; padding: 8px 16px; border-radius: 6px; font-weight: normal; }}"
    "</style>"
    '<div style="background: #ffffff; color: #2d3b45; padding: 16px; border-radius: 8px; user-select: none; '
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
        st.caption(
            "This is only a preview, so don't copy from the preview. "
            "Use the copy button on the HTML box below."
        )
        st.html(_PREVIEW_FRAME.format(page=page_html))
    st.markdown("**HTML to paste**")
    st.code(page_html, language="html")
