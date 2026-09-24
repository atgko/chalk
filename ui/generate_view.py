"""Generate tab — a wired shell until Milestone 7 lands the generators
(PLAN.md Risk #2): the pickers are real, the Generate button is not yet."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from chalk.models import CourseData
from chalk.project import ProjectPaths, list_source_files

CONTENT_TYPES = ("Quiz", "Discussion prompts", "Rubric", "Module summary", "Slides")


def render(paths: ProjectPaths, course_data: CourseData) -> None:
    st.info("Content generation arrives in the next update. Extraction, rollover, and export all work now.")
    st.selectbox("Content type", CONTENT_TYPES)
    weeks = {w.week_number: w for w in course_data.weeks if not w.is_break}
    st.selectbox(
        "Week",
        list(weeks),
        format_func=lambda n: f"Week {n} — {'; '.join(weeks[n].topics) or 'no topics listed'}",
    )

    syllabus_name = Path(course_data.course.source_file).name
    materials = [name for name in list_source_files(paths) if name != syllabus_name]
    if materials:
        st.multiselect("Source materials to use", materials)
    else:
        st.caption("No source materials added yet — generation will use course topics and objectives only.")

    st.button("Generate", type="primary", disabled=True)
