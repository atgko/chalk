"""Shared rollover computation and preview structure (F-02).

`roll_over_course()` is the pure core: given a course's extracted data and
a target term, it computes a new CourseData with shifted dates (and, for
a duration change, added/removed weeks) plus a RolloverPreview describing
every change and any flags that need human confirmation before anything
is written to disk. It never touches a file — chalk.rollover.docx_rollover
and chalk.rollover.markdown_rollover use its output to actually rewrite a
syllabus in each format.

Algorithm (validated against the PRD's own worked example, section 6.2 —
IS 6640, Fall 2026 -> Fall 2027):
- Week 1 anchors to the target term's start date.
- Each subsequent regular week's date is `new_term_start + 7 * (week_number - 1)`
  days — a pure instructional-week counter, unaffected by where breaks
  fall. This matches the worked example exactly: every week shifts by the
  same number of days Week 1 did (Aug 24 -> Aug 23 is -1 day; so is every
  later week).
- Each break week's dates come from the target term's own calendar data
  (matched by label), not from shifting the original break's dates —
  breaks move independently of the instructional-week counter from year
  to year (Fall Break isn't always exactly 7*N days after Week 1).
- After computing every week's new date, any regular week whose date
  falls inside one of the target term's break windows is flagged for
  human confirmation rather than silently rescheduled — reproducing the
  worked example's "Fall Break 2027 is Oct 9-17 — confirm Week 8 timing".
  When the instructor gives the target term's meeting days, only a
  holiday or break that lands on an actual class day is flagged.
- Breaks the instructor says the class meets through (some graduate
  programs hold class over Fall/Spring Break) are dropped from the
  schedule and never flagged.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from chalk.calendar_data import find_term
from chalk.errors import LLMProviderError
from chalk.llm_client import complete
from chalk.models import CourseData, UniversityDate, Week
from chalk.rollover.flags import (
    duration_change_flags,
    flag_dst_boundary_weeks,
    flag_numbered_weeks_marked_as_breaks,
    flag_weeks_colliding_with_target_breaks,
    schedule_choice_flags,
)
from chalk.rollover.season_change import (
    holiday_names,
    is_holiday_name,
    is_season_change,
    match_calendar_entry,
    missing_holiday_flag,
    multi_day_breaks,
    rebuild_break_weeks,
    replacement_flag,
    single_day_holidays,
    stale_break_flag,
    unmatched_university_date_flag,
)

# Word boundaries, so "Independence Day" isn't read as the end of term.
_TERM_BEGINS_RE = re.compile(r"\bbegin", re.IGNORECASE)
_TERM_ENDS_RE = re.compile(r"\bend", re.IGNORECASE)

# Stand-in date for weeks added by a duration increase — overwritten by
# _shift_regular_weeks, and reported as "no old date" in the preview.
_PLACEHOLDER_DATE = dt.date(1900, 1, 1)


@dataclass
class WeekChange:
    week_number: int | None
    label: str
    old_date: dt.date | None
    new_date: dt.date | None
    flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RolloverPreview:
    source_term: str
    target_term: str
    source_duration_weeks: int
    target_duration_weeks: int
    week_changes: list[WeekChange]
    general_flags: list[str] = field(default_factory=list)


def roll_over_course(
    course_data: CourseData,
    *,
    target_term: str,
    calendars: dict,
    target_duration_weeks: int | None = None,
    manual_week1_date: dt.date | None = None,
    llm_generate_topics: bool = True,
    meeting_days: tuple[int, ...] = (),
    breaks_not_observed: frozenset[str] = frozenset(),
) -> tuple[CourseData, RolloverPreview]:
    """Compute a rolled-over CourseData and its RolloverPreview.

    `target_duration_weeks` defaults to the course's current duration (no
    change). If it's larger than the current duration and
    `llm_generate_topics` is True, the extra weeks get LLM-drafted
    placeholder topics (DECISIONS.md); if the LLM is unavailable, they get
    an explicit "no LLM available" placeholder instead — this is the one
    rollover sub-case that touches the network, and it must degrade
    gracefully rather than fail the whole rollover (PRD section 10's
    offline guarantee).

    `manual_week1_date` is used when `target_term` isn't found in
    `calendars` (graceful degradation, PRD section 5.3). Raises ValueError
    if the term isn't found and no manual date was given.

    `meeting_days` (weekday numbers, 0 = Monday) narrows the holiday and
    break warnings to days the class actually meets; empty keeps the old
    check against each week's start date. `breaks_not_observed` names
    target-calendar breaks (by label, e.g. "Fall Break") the class meets
    through: they're dropped from the schedule and never flagged.
    """
    old_duration = course_data.course.duration_weeks
    new_duration = target_duration_weeks or old_duration

    term_data = find_term(calendars, target_term)
    if term_data is not None:
        new_term_start = dt.date.fromisoformat(term_data["start"])
    elif manual_week1_date is not None:
        new_term_start = manual_week1_date
    else:
        raise ValueError(
            f"Term '{target_term}' is not in the calendar data and no manual "
            "Week 1 date was given."
        )
    calendar_breaks = term_data["no_class_dates"] if term_data else []
    target_breaks = [entry for entry in calendar_breaks if entry["label"] not in breaks_not_observed]

    regular_weeks = _adjust_regular_week_count(
        [week for week in course_data.weeks if not week.is_break], new_duration, llm_generate_topics
    )
    syllabus_break_weeks = [week for week in course_data.weeks if week.is_break]
    original_break_weeks, dropped_breaks = _drop_breaks_not_observed(
        syllabus_break_weeks, calendar_breaks, breaks_not_observed
    )

    season_changed = is_season_change(course_data.course.term, target_term)
    general_flags = duration_change_flags(old_duration, new_duration)
    general_flags.extend(schedule_choice_flags(course_data, meeting_days, breaks_not_observed, dropped_breaks))

    new_weeks, week_changes = _shift_regular_weeks(regular_weeks, new_term_start)
    if season_changed and syllabus_break_weeks and term_data is not None:
        new_break_weeks, break_changes = _rebuild_break_weeks_for_new_season(target_breaks, new_weeks)
        general_flags.append(
            replacement_flag(
                course_data.course.term,
                target_term,
                removed=[break_name(week.label) for week in original_break_weeks],
                added=[break_name(week.label) for week in new_break_weeks],
            )
        )
    else:
        new_break_weeks, break_changes = _shift_break_weeks(
            original_break_weeks, target_breaks, new_term_start, course_data.course.term_start
        )
        if season_changed and original_break_weeks:
            general_flags.append(
                stale_break_flag(
                    course_data.course.term,
                    target_term,
                    [break_name(week.label) for week in original_break_weeks],
                )
            )
    new_weeks.extend(new_break_weeks)
    week_changes.extend(break_changes)

    flag_weeks_colliding_with_target_breaks(
        new_weeks, week_changes, target_breaks, new_term_start.year, meeting_days
    )
    flag_numbered_weeks_marked_as_breaks(new_weeks, week_changes, course_data.course.term, target_term)

    if course_data.course.source_format == "markdown":
        flag_dst_boundary_weeks(new_weeks, week_changes)

    new_weeks.sort(key=_week_sort_key)

    new_university_dates, university_date_flags = _shift_university_dates(
        course_data.university_dates,
        term_data,
        calendar_breaks,
        new_term_start,
        course_data.course.term_start,
        rename_for_term=target_term if season_changed else None,
        known_holidays=holiday_names(calendars),
    )
    general_flags.extend(university_date_flags)

    new_course_info = course_data.course.model_copy(
        update={
            "term": target_term,
            "term_start": new_term_start,
            "term_end": _course_end_date(new_weeks),
            "duration_weeks": new_duration,
        }
    )
    new_course_data = course_data.model_copy(
        update={
            "course": new_course_info,
            "weeks": new_weeks,
            "university_dates": new_university_dates,
        }
    )

    preview = RolloverPreview(
        source_term=course_data.course.term,
        target_term=target_term,
        source_duration_weeks=old_duration,
        target_duration_weeks=new_duration,
        week_changes=week_changes,
        general_flags=general_flags,
    )
    return new_course_data, preview


# ---- Regular week count (duration change) ----------------------------------


def _adjust_regular_week_count(
    regular_weeks: list[Week], new_duration: int, llm_generate_topics: bool
) -> list[Week]:
    current = len(regular_weeks)
    if new_duration <= current:
        return regular_weeks[:new_duration]
    return regular_weeks + _build_placeholder_weeks(
        range(current + 1, new_duration + 1), regular_weeks, llm_generate_topics
    )


def _build_placeholder_weeks(
    week_numbers: range, existing_weeks: list[Week], llm_generate_topics: bool
) -> list[Week]:
    placeholders = []
    for week_number in week_numbers:
        topics = _draft_topics_for_new_week(week_number, existing_weeks) if llm_generate_topics else []
        notes = (
            "AI-generated draft — review and edit before use."
            if topics
            else "No LLM available — fill in this week's content manually."
        )
        placeholders.append(
            Week(
                week_number=week_number,
                date=_PLACEHOLDER_DATE,
                label=f"Week {week_number}",
                is_break=False,
                topics=topics,
                assignments=[],
                notes=notes,
            )
        )
    return placeholders


def _draft_topics_for_new_week(week_number: int, existing_weeks: list[Week]) -> list[str]:
    """Ask the LLM for plausible placeholder topics for a newly-added
    week. Degrades to an empty list (never raises) if the LLM is
    unavailable."""
    recent_topics = ", ".join(
        topic for week in existing_weeks[-3:] for topic in week.topics if week.topics
    )
    prompt = (
        f"A university course schedule is being extended by a new Week {week_number}. "
        f"Recent weeks covered: {recent_topics or 'not specified'}. "
        "Suggest 2-3 plausible topic names for this new week, one per line, "
        "no numbering, no extra commentary."
    )
    try:
        result = complete(prompt, max_tokens=100)
    except LLMProviderError:
        return []
    return [line.strip("-* ").strip() for line in result["text"].splitlines() if line.strip()]


# ---- Date shifting -----------------------------------------------------------


def _shift_regular_weeks(
    regular_weeks: list[Week], new_term_start: dt.date
) -> tuple[list[Week], list[WeekChange]]:
    new_weeks: list[Week] = []
    changes: list[WeekChange] = []
    for week in regular_weeks:
        new_date = new_term_start + dt.timedelta(days=7 * (week.week_number - 1))
        new_label = f"Week {week.week_number} ({new_date.month}/{new_date.day})"
        new_weeks.append(week.model_copy(update={"date": new_date, "label": new_label}))
        changes.append(
            WeekChange(
                week_number=week.week_number,
                label=new_label,
                old_date=None if week.date == _PLACEHOLDER_DATE else week.date,
                new_date=new_date,
            )
        )
    return new_weeks, changes


def _shift_break_weeks(
    break_weeks: list[Week],
    target_breaks: list[dict],
    new_term_start: dt.date,
    old_term_start: dt.date,
) -> tuple[list[Week], list[WeekChange]]:
    new_weeks: list[Week] = []
    changes: list[WeekChange] = []
    offset_days = (new_term_start - old_term_start).days

    for week in break_weeks:
        matched = _match_break_in_calendar(week.label, target_breaks)
        if matched is not None:
            new_start = dt.date.fromisoformat(matched["date_start"])
            new_end = dt.date.fromisoformat(matched["date_end"])
        else:
            new_start = week.date_start + dt.timedelta(days=offset_days)
            new_end = week.date_end + dt.timedelta(days=offset_days)

        # Refresh the label's embedded date text too -- otherwise a break
        # rolled onto a new term keeps displaying its *old* dates even
        # though date_start/date_end were correctly updated.
        new_label = (
            f"{break_name(week.label)} "
            f"({new_start.month}/{new_start.day} - {new_end.month}/{new_end.day})"
        )
        new_weeks.append(
            week.model_copy(update={"date_start": new_start, "date_end": new_end, "label": new_label})
        )
        changes.append(
            WeekChange(
                week_number=None,
                label=new_label,
                old_date=week.date_start,
                new_date=new_start,
            )
        )
    return new_weeks, changes


def _rebuild_break_weeks_for_new_season(
    target_breaks: list[dict], new_regular_weeks: list[Week]
) -> tuple[list[Week], list[WeekChange]]:
    """Season-change rollover: break rows come from the target calendar
    (chalk.rollover.season_change), so none of them has an "old" date."""
    new_break_weeks = rebuild_break_weeks(target_breaks, new_regular_weeks)
    changes = [
        WeekChange(week_number=None, label=week.label, old_date=None, new_date=week.date_start)
        for week in new_break_weeks
    ]
    return new_break_weeks, changes


def _drop_breaks_not_observed(
    break_weeks: list[Week], calendar_breaks: list[dict], breaks_not_observed: frozenset[str]
) -> tuple[list[Week], list[str]]:
    """Split the syllabus's break rows into (kept, names of dropped ones)."""
    skipped = [entry for entry in calendar_breaks if entry["label"] in breaks_not_observed]
    kept = [week for week in break_weeks if _match_break_in_calendar(week.label, skipped) is None]
    dropped = [break_name(week.label) for week in break_weeks if week not in kept]
    return kept, dropped


# ---- University dates ---------------------------------------------------


def _shift_university_dates(
    university_dates: list[UniversityDate],
    term_data: dict | None,
    target_breaks: list[dict],
    new_term_start: dt.date,
    old_term_start: dt.date,
    *,
    rename_for_term: str | None = None,
    known_holidays: frozenset[str] = frozenset(),
) -> tuple[list[UniversityDate], list[str]]:
    """Recompute the university-dates table for the target term: "begin"
    and "end" entries come from the target term's own start/end, entries
    matching a named break or holiday come from its target-term dates, and
    anything else falls back to a same-offset shift as a best effort.

    `rename_for_term` is set on a season-change rollover: an unmatched
    break span takes over the next unused target-term break, and an
    unmatched holiday (one named in `known_holidays`, e.g. Labor Day) the
    next unused target-term holiday, name and dates. Anything still
    unmatched is flagged for review, as is any target-term holiday left
    over. Entries keep their order and count either way, so the writers
    can pair them with the source table's rows by position. Returns
    (entries, flags).
    """
    offset_days = (new_term_start - old_term_start).days
    target_holidays = single_day_holidays(target_breaks)
    unused_breaks = _calendar_entries_not_named_in(university_dates, multi_day_breaks(target_breaks))
    unused_holidays = _calendar_entries_not_named_in(university_dates, target_holidays)
    renaming = rename_for_term is not None and term_data is not None
    new_entries = []
    flags: list[str] = []

    for entry in university_dates:
        new_entry = _university_date_from_calendar(entry, term_data, target_breaks, target_holidays)
        if new_entry is None and renaming:
            new_entry = _university_date_for_new_season(entry, unused_breaks, unused_holidays, known_holidays)
            if new_entry is None:
                flags.append(unmatched_university_date_flag(entry.event, rename_for_term))
        new_entries.append(new_entry or _shift_university_date_by_offset(entry, offset_days))

    had_holidays = any(is_holiday_name(entry.event, known_holidays) for entry in university_dates)
    if renaming and had_holidays and unused_holidays:
        flags.append(missing_holiday_flag(unused_holidays, rename_for_term))
    return new_entries, flags


def _university_date_from_calendar(
    entry: UniversityDate, term_data: dict | None, target_breaks: list[dict], target_holidays: list[dict]
) -> UniversityDate | None:
    """The entry with its target-term date, if the calendar names it."""
    if term_data is not None and _TERM_BEGINS_RE.search(entry.event):
        return entry.model_copy(update={"date": dt.date.fromisoformat(term_data["start"])})
    if term_data is not None and _TERM_ENDS_RE.search(entry.event):
        return entry.model_copy(update={"date": dt.date.fromisoformat(term_data["end"])})
    matched_break = _match_break_in_calendar(entry.event, target_breaks)
    if matched_break is not None:
        return _university_date_from_break(entry, matched_break, rename=False)
    matched_holiday = match_calendar_entry(entry.event, target_holidays)
    if matched_holiday is not None and entry.date is not None:
        return _university_date_from_holiday(entry, matched_holiday, rename=False)
    return None


def _university_date_for_new_season(
    entry: UniversityDate,
    unused_breaks: list[dict],
    unused_holidays: list[dict],
    known_holidays: frozenset[str],
) -> UniversityDate | None:
    """Season change: the entry renamed to the next unused target-term
    break or holiday of its kind; None if there's none to take over.
    Consumes the entry it takes from `unused_breaks`/`unused_holidays`."""
    if entry.date_start is not None and unused_breaks:
        return _university_date_from_break(entry, unused_breaks.pop(0), rename=True)
    is_holiday = entry.date is not None and is_holiday_name(entry.event, known_holidays)
    if is_holiday and unused_holidays:
        return _university_date_from_holiday(entry, unused_holidays.pop(0), rename=True)
    return None


def _calendar_entries_not_named_in(
    university_dates: list[UniversityDate], calendar_entries: list[dict]
) -> list[dict]:
    named = [match_calendar_entry(entry.event, calendar_entries) for entry in university_dates]
    return [entry for entry in calendar_entries if entry not in named]


def _university_date_from_break(entry: UniversityDate, target_break: dict, *, rename: bool) -> UniversityDate:
    updates = {
        "date": None,
        "date_start": dt.date.fromisoformat(target_break["date_start"]),
        "date_end": dt.date.fromisoformat(target_break["date_end"]),
    }
    if rename:
        updates["event"] = target_break["label"]
    return entry.model_copy(update=updates)


def _university_date_from_holiday(entry: UniversityDate, holiday: dict, *, rename: bool) -> UniversityDate:
    updates = {"date": dt.date.fromisoformat(holiday["date"])}
    if rename:
        updates["event"] = holiday["label"]
    return entry.model_copy(update=updates)


def _shift_university_date_by_offset(entry: UniversityDate, offset_days: int) -> UniversityDate:
    updates = {}
    if entry.date is not None:
        updates["date"] = entry.date + dt.timedelta(days=offset_days)
    if entry.date_start is not None:
        updates["date_start"] = entry.date_start + dt.timedelta(days=offset_days)
    if entry.date_end is not None:
        updates["date_end"] = entry.date_end + dt.timedelta(days=offset_days)
    return entry.model_copy(update=updates)


def _match_break_in_calendar(label: str, target_breaks: list[dict]) -> dict | None:
    return match_calendar_entry(label, multi_day_breaks(target_breaks))


_PARENTHETICAL_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


def break_name(label: str) -> str:
    """Strip a trailing "(...)" date parenthetical from a break's label,
    e.g. "Fall Break (10/10 - 10/18)" -> "Fall Break", so a fresh date
    range can be appended for the new term."""
    stripped = _PARENTHETICAL_SUFFIX_RE.sub("", label).strip()
    return stripped or label


# ---- Small shared helpers ------------------------------------------------


def _week_sort_key(week: Week) -> dt.date:
    return week.date if week.date is not None else week.date_start


def _course_end_date(weeks: list[Week]) -> dt.date:
    last = weeks[-1]
    return last.date if last.date is not None else last.date_end
