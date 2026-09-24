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
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from chalk.calendar_data import find_term
from chalk.errors import LLMProviderError
from chalk.llm_client import complete
from chalk.models import CourseData, UniversityDate, Week

_DST_BOUNDARY_WINDOW_DAYS = 14

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
    target_breaks = term_data["no_class_dates"] if term_data else []

    regular_weeks = _adjust_regular_week_count(
        [week for week in course_data.weeks if not week.is_break], new_duration, llm_generate_topics
    )
    original_break_weeks = [week for week in course_data.weeks if week.is_break]

    new_weeks, week_changes = _shift_regular_weeks(regular_weeks, new_term_start)
    new_break_weeks, break_changes = _shift_break_weeks(
        original_break_weeks, target_breaks, new_term_start, course_data.course.term_start
    )
    new_weeks.extend(new_break_weeks)
    week_changes.extend(break_changes)

    _flag_weeks_colliding_with_target_breaks(new_weeks, week_changes, target_breaks, new_term_start.year)

    general_flags = _general_flags(old_duration, new_duration)

    if course_data.course.source_format == "markdown":
        _flag_dst_boundary_weeks(new_weeks, week_changes)

    new_weeks.sort(key=_week_sort_key)

    new_university_dates = _shift_university_dates(
        course_data.university_dates,
        term_data,
        target_breaks,
        new_term_start,
        course_data.course.term_start,
    )

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


# ---- University dates ---------------------------------------------------


def _shift_university_dates(
    university_dates: list[UniversityDate],
    term_data: dict | None,
    target_breaks: list[dict],
    new_term_start: dt.date,
    old_term_start: dt.date,
) -> list[UniversityDate]:
    """Recompute the university-dates table for the target term: "begin"
    and "end" entries come from the target term's own start/end, entries
    matching a named break come from that break's target-term dates, and
    anything else falls back to a same-offset shift as a best effort."""
    offset_days = (new_term_start - old_term_start).days
    new_entries = []

    for entry in university_dates:
        event_lower = entry.event.lower()
        if term_data is not None and "begin" in event_lower:
            new_entries.append(entry.model_copy(update={"date": dt.date.fromisoformat(term_data["start"])}))
            continue
        if term_data is not None and "end" in event_lower:
            new_entries.append(entry.model_copy(update={"date": dt.date.fromisoformat(term_data["end"])}))
            continue

        matched = _match_break_in_calendar(entry.event, target_breaks)
        if matched is not None:
            new_entries.append(
                entry.model_copy(
                    update={
                        "date": None,
                        "date_start": dt.date.fromisoformat(matched["date_start"]),
                        "date_end": dt.date.fromisoformat(matched["date_end"]),
                    }
                )
            )
            continue

        new_entries.append(_shift_university_date_by_offset(entry, offset_days))

    return new_entries


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
    normalized_label = _normalize_break_label(label)
    for entry in target_breaks:
        if "date_start" not in entry or "date_end" not in entry:
            continue  # a single-day holiday (e.g. Labor Day), not a break span
        normalized_entry = _normalize_break_label(entry["label"])
        if normalized_entry in normalized_label or normalized_label in normalized_entry:
            return entry
    return None


def _normalize_break_label(label: str) -> str:
    return re.sub(r"[^a-z ]", "", label.lower()).strip()


_PARENTHETICAL_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


def break_name(label: str) -> str:
    """Strip a trailing "(...)" date parenthetical from a break's label,
    e.g. "Fall Break (10/10 - 10/18)" -> "Fall Break", so a fresh date
    range can be appended for the new term."""
    stripped = _PARENTHETICAL_SUFFIX_RE.sub("", label).strip()
    return stripped or label


# ---- Flags -------------------------------------------------------------------


def _flag_weeks_colliding_with_target_breaks(
    weeks: list[Week], changes: list[WeekChange], target_breaks: list[dict], year: int
) -> None:
    changes_by_week_number = {c.week_number: c for c in changes if c.week_number is not None}
    for week in weeks:
        if week.is_break or week.date is None:
            continue
        for entry in target_breaks:
            if _date_in_break(week.date, entry):
                changes_by_week_number[week.week_number].flags.append(
                    f"{entry['label']} {year} is {_format_break_range(entry)} — "
                    f"confirm Week {week.week_number} timing"
                )


def _date_in_break(date: dt.date, entry: dict) -> bool:
    if "date" in entry:
        return date == dt.date.fromisoformat(entry["date"])
    if "date_start" in entry and "date_end" in entry:
        return dt.date.fromisoformat(entry["date_start"]) <= date <= dt.date.fromisoformat(
            entry["date_end"]
        )
    return False  # pragma: no cover - calendars.json entries always have one or the other


def _format_break_range(entry: dict) -> str:
    if "date" in entry:
        d = dt.date.fromisoformat(entry["date"])
        return f"{d.strftime('%b')} {d.day}"
    start = dt.date.fromisoformat(entry["date_start"])
    end = dt.date.fromisoformat(entry["date_end"])
    return f"{start.strftime('%b')} {start.day}–{end.day}"


def _general_flags(old_duration: int, new_duration: int) -> list[str]:
    if old_duration == new_duration:
        return []
    return [
        f"Course length changed from {old_duration} to {new_duration} weeks. "
        "Review quiz, exam, and lab numbering in the assignments below — "
        "the tool never renumbers them automatically."
    ]


def _first_sunday_of_november(year: int) -> dt.date:
    november_first = dt.date(year, 11, 1)
    days_until_sunday = (6 - november_first.weekday()) % 7
    return november_first + dt.timedelta(days=days_until_sunday)


def _flag_dst_boundary_weeks(weeks: list[Week], changes: list[WeekChange]) -> None:
    """Markdown-only (PRD section 6.2): flag any week with assignments
    that falls within two weeks of the DST boundary, for human review.
    Never automates a timezone suffix."""
    changes_by_week_number = {c.week_number: c for c in changes if c.week_number is not None}
    for week in weeks:
        if week.is_break or week.date is None or not week.assignments:
            continue
        boundary = _first_sunday_of_november(week.date.year)
        if abs((week.date - boundary).days) <= _DST_BOUNDARY_WINDOW_DAYS:
            changes_by_week_number[week.week_number].flags.append(
                "This week's assignments fall within two weeks of the DST "
                "boundary (first Sunday of November). Double-check due "
                "times/timezones by hand — this is never automated."
            )


# ---- Small shared helpers ------------------------------------------------


def _week_sort_key(week: Week) -> dt.date:
    return week.date if week.date is not None else week.date_start


def _course_end_date(weeks: list[Week]) -> dt.date:
    last = weeks[-1]
    return last.date if last.date is not None else last.date_end
