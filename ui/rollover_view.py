"""Rollover tab (PRD section 7.2 / F-02): pick a target term, preview
every date change and flag, and only then confirm and write files.

The preview runs in the background, since drafting topics for added weeks
calls the AI and shouldn't stop if the instructor switches tabs."""

from __future__ import annotations

import datetime as dt

import streamlit as st

from chalk.calendar_data import find_term, load_calendars, suggest_target_term
from chalk.config import env_is_configured
from chalk.errors import ChalkError, TermNotInCalendarError
from chalk.models import CourseData
from chalk.pipeline import RolloverPlan, confirm_rollover, preview_rollover
from chalk.progress import ProgressCallback
from chalk.project import ProjectPaths
from chalk.rollover.meeting_days import DAY_ABBREVIATIONS, parse_meeting_days
from chalk.rollover.season_change import multi_day_breaks
from chalk.sessions import (
    FULL_TERM,
    SessionSpan,
    available_spans,
    guess_session,
    is_summer,
    session_start,
)
from ui import background, common, session, tables
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

    inputs = (
        term,
        week1_date,
        duration,
        use_llm,
        meeting_days,
        breaks_not_observed,
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
        for path in written:
            common.download_button(path, paths, key_prefix="rollover")


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
    """Meeting days (so holiday warnings only fire on real class days) and
    which of the target term's breaks the class actually takes off."""
    day_names = st.multiselect(
        "Class meets on",
        DAY_ABBREVIATIONS,
        default=[DAY_ABBREVIATIONS[day] for day in parse_meeting_days(course_data.course.meeting_pattern)],
        help="Holiday and break warnings are only shown for weeks where one lands on a class day. "
        "Leave empty to check each week's start date instead.",
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
    term, week1_date, duration, use_llm, meeting_days, breaks_not_observed = inputs[:6]
    plan = preview_rollover(
        paths,
        course_data,
        term,
        target_duration_weeks=duration,
        manual_week1_date=week1_date,
        llm_generate_topics=use_llm,
        meeting_days=meeting_days,
        breaks_not_observed=breaks_not_observed,
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
    if elsewhere:
        background.finished_elsewhere(_TAB, f"The rollover preview for {stored.inputs[0]} is ready on the Rollover tab.")
        st.rerun()


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
    for change in preview.week_changes:
        for flag in change.flags:
            st.warning(flag)
    st.dataframe(tables.preview_rows(preview), hide_index=True)
    st.markdown(
        "**Files to be written:**  \n"
        + "  \n".join(f"`{common.relative(path, paths)}`" for path in plan.files_to_write)
    )

    confirm_col, cancel_col = st.columns(2)
    if confirm_col.button("Confirm rollover", type="primary"):
        try:
            written = confirm_rollover(paths, plan)
        except ChalkError as exc:
            st.error(exc.user_message)
            return
        session.set_rollover_plan(None)
        session.set_rollover_written(written)
        st.rerun()
    if cancel_col.button("Cancel", key="cancel-rollover"):
        session.set_rollover_plan(None)
        st.rerun()
