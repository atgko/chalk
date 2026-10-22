"""Review tab (PRD section 7.2): show the extracted (or saved) course in
readable form, let the instructor correct duration_weeks and the course
details (which a real syllabus often leaves partly unlabeled, so some
arrive blank), and save course.json + the course brief on "Confirm and
save"."""

from __future__ import annotations

import datetime as dt
import re

import streamlit as st

from chalk.calendar_data import find_term, load_calendars
from chalk.errors import ChalkError
from chalk.extractors.consistency import grading_weight_warning
from chalk.extractors.undated_schedule import date_undated_schedule
from chalk.models import CourseData
from chalk.pipeline import save_reviewed_course
from chalk.project import ProjectPaths
from chalk.sessions import FULL_TERM, available_spans, guess_session, session_start
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

    st.caption("Newly extracted — not saved yet." if pending else "Showing the saved course.")
    details = _render_course_details(course_data)
    course_data = _render_week1_date(paths, course_data)
    duration = _render_duration(course_data)
    _render_lists(course_data)

    save_col, discard_col = st.columns(2)
    if pending is not None and discard_col.button("Discard", key="discard-extraction"):
        session.set_pending_extraction(None)
        session.flash(
            "Discarded the new extraction. Nothing was saved."
            if saved_course is None
            else "Discarded the new extraction. The saved course is unchanged."
        )
        st.rerun()
    if save_col.button("Confirm and save", type="primary"):
        credits_error = _credits_error(details["credits"])
        if credits_error:
            st.error(credits_error)
            return
        details["credits"] = _credits_value(details["credits"])
        updated = course_data.model_copy(
            update={"course": course_data.course.model_copy(update={**details, "duration_weeks": duration})}
        )
        try:
            save_reviewed_course(paths, updated)
        except ChalkError as exc:
            st.error(exc.user_message)
            return
        session.set_pending_extraction(None)
        session.set_rollover_plan(None)
        session.flash("Saved the course and updated the course brief.")
        st.rerun()


_DETAIL_FIELDS = (
    ("title", "Course title"),
    ("number", "Course number"),
    ("section", "Section"),
    ("credits", "Credits"),
    ("instructor", "Instructor"),
    ("meeting_pattern", "Meeting pattern"),
)


def _render_course_details(course_data: CourseData) -> dict:
    """Editable course details; returns the entered values (credits still
    as text — validated on save)."""
    course = course_data.course
    st.subheader(course.title)
    st.markdown(f"**Term:** {course.term}  \n**Source:** {course.source_file}")
    current = course.model_dump()
    if any(current[name] in ("", None) for name, _label in _DETAIL_FIELDS):
        st.caption("Blank fields weren't found in the syllabus — fill them in here.")
    details = {}
    columns = st.columns(3)
    for index, (name, label) in enumerate(_DETAIL_FIELDS):
        value = "" if current[name] is None else (f"{current[name]:g}" if name == "credits" else str(current[name]))
        details[name] = columns[index % 3].text_input(label, value=value).strip()
    details["title"] = details["title"] or course.title  # never save a blank title
    return details


def _render_week1_date(paths: ProjectPaths, course_data: CourseData) -> CourseData:
    """A schedule with no dates of its own was dated by Chalk: show from
    when, and let the instructor change Week 1, which re-dates the rest."""
    if not course_data.course.undated_schedule:
        return course_data
    current = next(week.date for week in course_data.weeks if not week.is_break)
    st.info(
        "This syllabus's schedule has no dates, so Chalk dated the weeks one week apart from the "
        "first day of the term, skipping breaks. Check the date of the first class.",
        icon="📅",
    )
    calendars = load_calendars(paths.calendars_json)
    # Keyed to this extraction, so a choice made for one upload doesn't carry over to the next.
    key = course_data.course.extracted_at.isoformat()
    suggested = _session_week1(course_data, calendars, key) or current
    week1 = st.date_input("Week 1 date", value=suggested, format="MM/DD/YYYY", key=f"undated-week1-{key}-{suggested}")
    if not isinstance(week1, dt.date) or week1 == current:
        return course_data
    return date_undated_schedule(course_data, week1, calendars)


def _session_week1(course_data: CourseData, calendars: dict, key: str) -> dt.date | None:
    """For a term in the calendar, ask which 5-week session the course
    starts in (chalk/sessions.py); returns that session's first day, or
    None for the full term."""
    entry = find_term(calendars, course_data.course.term)
    if entry is None:
        return None
    spans = available_spans(entry)
    regular_weeks = sum(1 for week in course_data.weeks if not week.is_break)
    guess = guess_session(regular_weeks, course_data.course.credits)
    span = st.selectbox(
        "Session",
        spans,
        index=spans.index(guess) if guess in spans else spans.index(FULL_TERM),
        format_func=lambda option: option.label,
        key=f"undated-session-{key}",
        help="Some programs split the term into three 5-week sessions. Pick the one this course "
        "starts in to set Week 1; a 1.5-credit course is one session.",
    )
    return None if span.first == 1 else session_start(entry, span.first)


_CREDITS_TEXT_RE = re.compile(r"^\d{1,2}(\.\d{1,2})?$")


def _credits_error(credits_text: str) -> str | None:
    if credits_text and not _CREDITS_TEXT_RE.match(credits_text):
        return f"Credits must be a number like 3 or 1.5 (got '{credits_text}'). Leave it blank if unknown."
    return None


def _credits_value(credits_text: str) -> int | float | None:
    if not credits_text:
        return None
    value = float(credits_text)
    return int(value) if value.is_integer() else value


def _render_duration(course_data: CourseData) -> int:
    course = course_data.course
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
        weight_warning = grading_weight_warning(course_data)
        if weight_warning:
            st.warning(weight_warning)
    else:
        st.caption("None found in the syllabus.")

    st.markdown("#### Week by week")
    st.dataframe(tables.week_rows(course_data), hide_index=True)

    if course_data.university_dates:
        st.markdown("#### University dates")
        st.dataframe(tables.university_date_rows(course_data), hide_index=True)
