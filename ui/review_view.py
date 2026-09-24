"""Review tab (PRD section 7.2): show the extracted (or saved) course in
readable form, let the instructor correct duration_weeks, and save
course.json + the course brief on "Confirm and save"."""

from __future__ import annotations

import streamlit as st

from chalk.errors import ChalkError
from chalk.models import CourseData
from chalk.pipeline import save_reviewed_course
from chalk.project import ProjectPaths
from ui import session, tables


def render(paths: ProjectPaths, saved_course: CourseData | None) -> None:
    pending = session.get_pending_extraction()
    if pending is not None and not pending.acknowledged:
        st.info("Resolve the term/schedule warning on the Upload tab first.")
        return

    course_data = pending.course_data if pending is not None else saved_course
    if course_data is None:
        st.info("Upload and extract a syllabus first.")
        return

    st.caption("Newly extracted — not saved yet." if pending else "Showing the saved course.json.")
    duration = _render_course_details(course_data)
    _render_lists(course_data)

    if st.button("Confirm and save", type="primary"):
        updated = course_data.model_copy(
            update={"course": course_data.course.model_copy(update={"duration_weeks": duration})}
        )
        try:
            save_reviewed_course(paths, updated)
        except ChalkError as exc:
            st.error(exc.user_message)
            return
        session.set_pending_extraction(None)
        session.set_rollover_plan(None)
        session.flash("Saved course.json and regenerated the course brief.")
        st.rerun()


def _render_course_details(course_data: CourseData) -> int:
    course = course_data.course
    st.subheader(course.title)
    left, middle, right = st.columns(3)
    left.markdown(f"**Course:** {course.number} (Section {course.section})  \n**Credits:** {course.credits}")
    middle.markdown(f"**Term:** {course.term}  \n**Meeting pattern:** {course.meeting_pattern}")
    right.markdown(f"**Instructor:** {course.instructor}  \n**Source:** {course.source_file}")

    schedule_weeks = tables.regular_week_count(course_data)
    duration = int(
        st.number_input(
            "Duration (weeks)",
            min_value=1,
            value=course.duration_weeks,
            step=1,
            help="Detected from the schedule. Change it to lengthen or shorten the course at rollover.",
        )
    )
    if duration != schedule_weeks:
        st.info(
            f"The schedule has {schedule_weeks} weeks. With duration set to {duration}, rollover will "
            f"{'add' if duration > schedule_weeks else 'drop'} {abs(duration - schedule_weeks)} week(s)."
        )
    return duration


def _render_lists(course_data: CourseData) -> None:
    st.markdown("#### Learning objectives")
    if course_data.learning_objectives:
        st.markdown("\n".join(f"{i}. {text}" for i, text in enumerate(course_data.learning_objectives, 1)))
    else:
        st.caption("None found in the syllabus.")

    st.markdown("#### Assessment weights")
    if course_data.assessments:
        st.dataframe(tables.assessment_rows(course_data), hide_index=True)
    else:
        st.caption("None found in the syllabus.")

    st.markdown("#### Week by week")
    st.dataframe(tables.week_rows(course_data), hide_index=True)

    if course_data.university_dates:
        st.markdown("#### University dates")
        st.dataframe(tables.university_date_rows(course_data), hide_index=True)
