"""Course sessions: a semester split into three 5-week blocks.

Some University of Utah programs run classes in sessions rather than the
whole semester (UAT of PR #18): Session 1 is the term's first five class
weeks, Session 2 the next five, Session 3 the last five. A course may run
for one session (a 1.5-credit class is one 5-week sprint), two in a row
(Sessions 1-2 or 2-3, 10 weeks), or all three (the full 15 weeks).

The registrar's calendar doesn't list session dates, so they're counted
from the term's first day of classes: five class weeks per session, where
a week inside a multi-day break (Fall Break, Spring Break) isn't a class
week. That's how the registrar's own half-terms fall around Fall Break
(first half ends Oct 9, second half begins Oct 19, 2026), and it makes
Fall 2026's Session 3 end in the last week of classes.

Summer is different: it's a compressed term with no sessions, and a
summer course runs either 10 or 12 weeks from the term's first day. So a
summer term offers those two lengths instead (`SUMMER_SPANS`).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from chalk.rollover.season_change import multi_day_breaks, season_of

SESSION_WEEKS = 5
SESSION_COUNT = 3
# Below this many credits a course is one 5-week session (e.g. 1.5 credits).
_SINGLE_SESSION_CREDITS = 2
# A summer course runs 12 weeks (the full summer term) or 10.
_FULL_SUMMER_WEEKS = 12
_SHORT_SUMMER_WEEKS = 10


@dataclass(frozen=True)
class SessionSpan:
    """Sessions `first` through `last` (1-3), e.g. 2-3. A summer length
    (`summer_weeks`, 10 or 12) has no sessions: it starts on the term's
    first day and runs that many weeks."""

    first: int
    last: int
    summer_weeks: int | None = None

    @property
    def weeks(self) -> int:
        if self.summer_weeks is not None:
            return self.summer_weeks
        return SESSION_WEEKS * (self.last - self.first + 1)

    @property
    def is_full_term(self) -> bool:
        """The whole semester, keeping the course's own length. A summer
        length always sets the length, so it's never this."""
        return self.summer_weeks is None and (self.first, self.last) == (1, SESSION_COUNT)

    @property
    def label(self) -> str:
        if self.summer_weeks is not None:
            return f"Full summer term ({self.weeks} weeks)" if self.weeks == _FULL_SUMMER_WEEKS else f"{self.weeks} weeks"
        if self.is_full_term:
            return "Full term (Sessions 1–3)"
        if self.first == self.last:
            return f"Session {self.first} ({self.weeks} weeks)"
        return f"Sessions {self.first}–{self.last} ({self.weeks} weeks)"

    @property
    def code(self) -> str:
        """The CLI's spelling: "2", "2-3"; a summer length is "--weeks"."""
        return str(self.first) if self.first == self.last else f"{self.first}-{self.last}"


def summer_length(weeks: int) -> SessionSpan:
    return SessionSpan(1, 1, summer_weeks=weeks)


FULL_TERM = SessionSpan(1, SESSION_COUNT)
SESSION_SPANS = (
    FULL_TERM,
    SessionSpan(1, 2),
    SessionSpan(2, 3),
    SessionSpan(1, 1),
    SessionSpan(2, 2),
    SessionSpan(3, 3),
)


SUMMER_SPANS = (summer_length(_FULL_SUMMER_WEEKS), summer_length(_SHORT_SUMMER_WEEKS))


def is_summer(term: str) -> bool:
    return (season_of(term) or "").lower() == "summer"


def parse_session(code: str) -> SessionSpan:
    """ "2" or "2-3" as a SessionSpan. Raises ValueError for anything else."""
    for span in SESSION_SPANS:
        if code.strip().replace("–", "-") == span.code:
            return span
    raise ValueError(f"'{code}' isn't a session: use 1, 2, 3, 1-2, 2-3, or 1-3.")


def session_start(term_entry: dict, session: int) -> dt.date:
    """The first day of `session` (1-3) in a calendar term: the term's
    start, moved on five class weeks per earlier session."""
    when = dt.date.fromisoformat(term_entry["start"])
    breaks = [
        (dt.date.fromisoformat(b["date_start"]), dt.date.fromisoformat(b["date_end"]))
        for b in multi_day_breaks(term_entry.get("no_class_dates", []))
    ]
    class_weeks = 0
    while class_weeks < SESSION_WEEKS * (session - 1):
        if not any(start <= when <= end for start, end in breaks):
            class_weeks += 1
        when += dt.timedelta(weeks=1)
    while any(start <= when <= end for start, end in breaks):  # a session never starts in a break
        when += dt.timedelta(weeks=1)
    return when


def available_spans(term_entry: dict) -> list[SessionSpan]:
    """The choices for a term: a summer term's two lengths (10 or 12
    weeks), else the session spans that fit in it, leaving out a session
    whose last class week starts after the term ends. The full term
    always fits: it's the whole term, however long."""
    if is_summer(term_entry["term"]):
        return list(SUMMER_SPANS)
    end = dt.date.fromisoformat(term_entry["end"])
    starts = {session: session_start(term_entry, session) for session in range(1, SESSION_COUNT + 1)}
    fits = {session for session, start in starts.items() if start + dt.timedelta(weeks=SESSION_WEEKS - 1) <= end}
    return [
        span
        for span in SESSION_SPANS
        if span.is_full_term or all(s in fits for s in range(span.first, span.last + 1))
    ]


def guess_session(week_count: int, credits: float | None = None, *, summer: bool = False) -> SessionSpan:
    """A likely span for a course: one session for a 1.5-credit or 5-week
    course, Sessions 1-2 for a 10-week one, else the full term, which
    keeps the course's own length. In summer: 10 weeks for a course of 10
    or fewer, else the full 12. Only a default; the instructor picks."""
    if summer:
        return summer_length(_SHORT_SUMMER_WEEKS if week_count <= _SHORT_SUMMER_WEEKS else _FULL_SUMMER_WEEKS)
    if (credits is not None and credits < _SINGLE_SESSION_CREDITS) or week_count == SESSION_WEEKS:
        return SessionSpan(1, 1)
    if week_count == 2 * SESSION_WEEKS:
        return SessionSpan(1, 2)
    return FULL_TERM
