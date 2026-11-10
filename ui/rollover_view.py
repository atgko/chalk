"""Rollover tab (PRD section 7.2 / F-02): pick a target term, preview
every date change and flag, and only then confirm and write files.

The preview runs in the background, since drafting topics for added weeks
calls the AI and shouldn't stop if the instructor switches tabs."""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

import streamlit as st

from chalk.calendar_data import find_term, load_calendars, suggest_target_term
from chalk.config import env_is_configured
from chalk.errors import ChalkError, TermNotInCalendarError
from chalk.links import url_for
from chalk.models import CourseData
from chalk.pipeline import RolloverPlan, confirm_rollover, missing_pdf_note, preview_rollover
from chalk.progress import ProgressCallback
from chalk.project import ProjectPaths
from chalk.rollover.break_weeks import MOVE_PAST_BREAKS_LABEL
from chalk.rollover.date_overrides import override_week_dates
from chalk.rollover.meeting_days import (
    DAY_ABBREVIATIONS,
    format_meeting_days,
    parse_meeting_days,
    schedule_meeting_days,
    usual_row_weekday,
)
from chalk.rollover.season_change import multi_day_breaks
from chalk.sessions import (
    FULL_TERM,
    SessionSpan,
    available_spans,
    guess_session,
    is_summer,
    session_start,
)
from ui import background, common, export_view, session, tables
from ui.session import StoredPlan

OTHER_TERM = "Another term (not in the calendar)"
_EARLIEST_WEEK1 = dt.date(2000, 1, 1)
_LATEST_WEEK1 = dt.date(2100, 12, 31)


_JOB = "rollover-preview"
_TAB = "Rollover"


def render(paths: ProjectPaths, course_data: CourseData) -> None:
    _apply_finished_job()
    error = background.pop_error(_TAB)
    if error:
        st.error(error)
    if background.is_running(_JOB):
        background.render_progress(_JOB)
        return

    term, week1_date = _render_term_inputs(paths, course_data)
    default_duration = course_data.course.duration_weeks
    if term and week1_date is None:  # a calendar term: it has sessions
        span, week1_date = _render_session_choice(paths, course_data, term)
        if not span.is_full_term:
            default_duration = span.weeks
    duration = int(st.number_input("Duration (weeks)", min_value=1, value=default_duration, step=1))
    use_llm = False
    if duration > tables.regular_week_count(course_data):
        use_llm = st.checkbox(
            "Draft topics for the added weeks with AI (clearly labeled as drafts)",
            value=env_is_configured(paths.env),
        )
    meeting_days, breaks_not_observed = _render_schedule_inputs(paths, course_data, term)
    move_past_breaks = st.checkbox(
        MOVE_PAST_BREAKS_LABEL,
        key="rollover-move-past-breaks",
        help="Ticked: when a break the class takes off covers every class day of a week, that week and the "
        "later ones move a week later, and the break gets a row in the schedule. Unticked, such a week "
        "is only flagged in the preview.",
    )
    class_time, location = _render_class_details(course_data, term)

    inputs = (
        term,
        week1_date,
        duration,
        use_llm,
        meeting_days,
        breaks_not_observed,
        class_time,
        location,
        move_past_breaks,
        course_data.course.term,
        course_data.course.extracted_at,
    )
    if st.button("Preview rollover", type="primary", disabled=not term):
        _preview(paths, course_data, inputs)

    stored = session.get_rollover_plan()
    if stored is not None and stored.inputs == inputs:
        _render_plan(paths, stored.plan)

    written = session.get_rollover_written()
    if written:
        st.success("Rollover complete. Previous versions were archived.")
        note = session.get_rollover_note()
        if note:
            st.info(note)
        _render_written(paths, written)


def _render_written(paths: ProjectPaths, written: list[Path]) -> None:
    """The files the rollover wrote, grouped and named as on the Export
    tab (UAT, Nov 4: a list of "Download outputs/..." buttons read as a
    mess). course.json is the project's own data, not a download."""
    outputs = [path for path in written if path.is_relative_to(paths.outputs_dir) and path.exists()]
    export_view.render_saved_location(paths, key_prefix="rollover")
    export_view.render_sections(paths, outputs, key_prefix="rollover")
    st.caption("These and every other output are also on the Export tab, with a download-everything zip.")


def _render_term_inputs(paths: ProjectPaths, course_data: CourseData) -> tuple[str, dt.date | None]:
    term_names = [t["term"] for t in load_calendars(paths.calendars_json).get("terms", [])]
    options = [*term_names, OTHER_TERM]
    suggested = suggest_target_term(course_data.course.term, term_names)
    selection = st.selectbox(
        "Target term", options, index=options.index(suggested) if suggested else len(options) - 1
    )
    if selection != OTHER_TERM:
        return selection, None

    st.info(TermNotInCalendarError().user_message)
    term = st.text_input("Term name", placeholder="Fall 2031").strip()
    # Streamlit's default range is only ~10 years either side of today.
    week1_date = st.date_input(
        "First day of classes", value=None, min_value=_EARLIEST_WEEK1, max_value=_LATEST_WEEK1
    )
    return (term if week1_date else ""), week1_date


def _render_session_choice(
    paths: ProjectPaths, course_data: CourseData, term: str
) -> tuple[SessionSpan, dt.date | None]:
    """Which 5-week sessions of `term` the course runs in (chalk/sessions.py),
    and the Week 1 date that means (None for the full term, which starts
    on the calendar's first day). Defaults to a guess from the course's
    length and credits."""
    entry = find_term(load_calendars(paths.calendars_json), term)
    spans = available_spans(entry)
    guess = guess_session(course_data.course.duration_weeks, course_data.course.credits, summer=is_summer(term))
    span = st.selectbox(
        "Session" if not is_summer(term) else "Summer length",
        spans,
        index=spans.index(guess) if guess in spans else spans.index(FULL_TERM),
        format_func=lambda option: option.label,
        key=f"session-{term}",
        help="Summer courses run 10 or 12 weeks from the first day of the term."
        if is_summer(term)
        else "Some programs split the term into three 5-week sessions. A 1.5-credit course is one session.",
    )
    if span.is_full_term:
        return span, None
    week1 = session_start(entry, span.first)
    if span.summer_weeks is None:
        st.caption(f"Session {span.first} of {term} starts {week1:%A, %B} {week1.day}.")
    return span, week1


def _render_schedule_inputs(
    paths: ProjectPaths, course_data: CourseData, term: str
) -> tuple[tuple[int, ...], frozenset[str]]:
    """Meeting days (so holiday warnings only fire on real class days, and
    a schedule with a row per class meeting is dated on them) and which of
    the target term's breaks the class actually takes off."""
    by_meeting = schedule_meeting_days(course_data.weeks)
    default_days = (
        parse_meeting_days(course_data.course.meeting_pattern) or by_meeting or usual_row_weekday(course_data.weeks)
    )
    help_text = (
        "Holiday and break warnings are only shown for weeks where one lands on a class day. "
        "A class with one row per week is dated on the first of these days in each week. "
        "Leave empty to keep each week's start date."
    )
    if by_meeting:
        help_text += (
            f" The schedule has a row per class meeting ({format_meeting_days(by_meeting)}): pick "
            "one day per meeting and each meeting is dated on its day in the new term."
        )
    day_names = st.multiselect(
        "Class meets on",
        DAY_ABBREVIATIONS,
        default=[DAY_ABBREVIATIONS[day] for day in default_days],
        help=help_text,
    )
    meeting_days = tuple(sorted(DAY_ABBREVIATIONS.index(name) for name in day_names))

    term_data = find_term(load_calendars(paths.calendars_json), term) if term else None
    breaks = multi_day_breaks(term_data["no_class_dates"]) if term_data else []
    not_observed = frozenset(
        entry["label"]
        for entry in breaks
        if not st.toggle(
            f"Class takes {entry['label']} off ({_short_range(entry)})",
            value=True,
            key=f"observe-break-{term}-{entry['label']}",
            help="Turn off if the class meets through this break (common in some graduate programs).",
        )
    )
    return meeting_days, not_observed


def _render_class_details(course_data: CourseData, term: str) -> tuple[str, str]:
    """The new term's class days and time (starting from the old ones) and
    location (starting blank: rooms are assigned each term). Rollover
    changes them wherever the syllabus repeats them (Nov 9 UAT)."""
    course = course_data.course
    st.markdown(f"**Class time and place{' in ' + term if term else ''}**")
    time_col, place_col = st.columns(2)
    class_time = time_col.text_input(
        "New class days and time",
        value=course.meeting_pattern,
        placeholder="e.g. Wed 6:00-8:45 pm",
        key=f"rollover-class-time-{course.extracted_at.isoformat()}",
        help="Changed everywhere the syllabus repeats the old class time. Other lines that mention a "
        "day and time are listed in the preview to check by hand.",
    )
    location = place_col.text_input(
        "New location",
        placeholder=f"Was: {course.location}" if course.location else "e.g. WEB L104, or Online",
        key=f"rollover-location-{course.extracted_at.isoformat()}",
        help="Rooms are assigned each term, so this starts blank. Left blank, the old location in the "
        "syllabus becomes TBA.",
    )
    st.caption(f"Find the new room and time in the [class schedule]({url_for('class_schedule')}).")
    return class_time, location


def _short_range(entry: dict) -> str:
    start = dt.date.fromisoformat(entry["date_start"])
    end = dt.date.fromisoformat(entry["date_end"])
    return f"{start.strftime('%b')} {start.day} – {end.strftime('%b')} {end.day}"


def _preview(paths: ProjectPaths, course_data: CourseData, inputs: tuple) -> None:
    background.start(
        _JOB, f"Computing the rollover to {inputs[0]}", _compute_plan, paths, course_data, inputs, tab=_TAB
    )
    st.rerun()


def _compute_plan(
    paths: ProjectPaths, course_data: CourseData, inputs: tuple, *, on_progress: ProgressCallback
) -> StoredPlan:
    """Runs on the background thread, so no Streamlit calls here."""
    term, week1_date, duration, use_llm, meeting_days, breaks_not_observed, class_time, location, move = inputs[:9]
    plan = preview_rollover(
        paths,
        course_data,
        term,
        target_duration_weeks=duration,
        manual_week1_date=week1_date,
        llm_generate_topics=use_llm,
        meeting_days=meeting_days,
        breaks_not_observed=breaks_not_observed,
        class_time=class_time,
        location=location,
        move_past_breaks=move,
        on_progress=on_progress,
    )
    return StoredPlan(inputs, plan)


def _apply_finished_job() -> None:
    future = background.take_finished(_JOB)
    if future is None:
        return
    elsewhere = session.active_tab() != _TAB
    try:
        stored = future.result()
    except ChalkError as exc:
        if elsewhere:
            background.finished_elsewhere(_TAB, f"Rollover preview failed: {exc.user_message}", failed=True)
            st.rerun()
        st.error(exc.user_message)
        return
    session.set_rollover_plan(stored)
    session.set_rollover_written([])
    st.session_state.pop(_DATES_KEY, None)  # a new preview starts from its own dates
    if elsewhere:
        background.finished_elsewhere(_TAB, f"The rollover preview for {stored.inputs[0]} is ready on the Rollover tab.")
        st.rerun()


_DATES_KEY = "rollover-new-dates"


def _render_editable_dates(plan: RolloverPlan) -> RolloverPlan:
    """The preview table, with each class week's new date editable (Nov 9
    UAT: instructors should be able to override a date that doesn't fit
    their class). Returns the plan with the instructor's dates applied."""
    edited = st.data_editor(
        tables.preview_date_rows(plan.preview),
        hide_index=True,
        disabled=("Week", "Current", "Check"),
        column_config={
            "New": st.column_config.DateColumn(
                "New",
                format="ddd MMM D",
                help="Click a date to change it. Break rows follow the calendar.",
            )
        },
        key=_DATES_KEY,
    )
    st.caption("To use a different date for a week, click its date under New and pick another.")
    rolled_over, preview = override_week_dates(plan.rolled_over, plan.preview, tables.edited_dates(edited))
    if preview is plan.preview:
        return plan
    st.info(preview.general_flags[-1])
    return dataclasses.replace(plan, rolled_over=rolled_over, preview=preview)


def _render_plan(paths: ProjectPaths, plan: RolloverPlan) -> None:
    preview = plan.preview
    st.subheader(
        f"Rollover preview: {plan.original.course.number or plan.original.course.title} "
        f"({preview.source_duration_weeks} weeks) → {preview.target_term}"
    )
    st.markdown(
        f'**Term label:** "{preview.source_term}" → "{preview.target_term}"  \n'
        f"**Duration:** {preview.source_duration_weeks} → {preview.target_duration_weeks} weeks"
    )
    for flag in preview.general_flags:
        st.warning(flag)
    for flag in preview.week_flags():
        st.warning(flag)
    plan = _render_editable_dates(plan)
    st.markdown(
        "**Files to be written:**  \n"
        + "  \n".join(
            f"{export_view.describe(path, paths)[1]}: `{common.relative(path, paths)}`"
            for path in plan.files_to_write
        )
    )

    confirm_col, cancel_col = st.columns(2)
    if confirm_col.button("Confirm rollover", type="primary"):
        try:
            with st.spinner("Writing the rolled-over files…"):
                written = confirm_rollover(paths, plan)
        except ChalkError as exc:
            st.error(exc.user_message)
            return
        session.set_rollover_plan(None)
        session.set_rollover_written(written, missing_pdf_note(plan, written))
        st.rerun()
    if cancel_col.button("Cancel", key="cancel-rollover"):
        session.set_rollover_plan(None)
        st.rerun()
