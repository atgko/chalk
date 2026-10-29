"""Classes that meet more than once a week.

Some syllabi give each class meeting its own schedule row and repeat the
week's number ("Week 2 (1/13)", "Week 2 (1/15)"), as an undergraduate
course that meets Tuesday and Thursday does (IS 4440, sponsor meeting,
Oct 28). It was read as 29 weeks. Each row stays its own Week, with its
own date and content, and `Week.meeting` numbers it within its week
(1, 2, ...), so rollover and the Word writer can tell the rows apart. The
course's length counts weeks, not rows. A schedule with one row per week
leaves `meeting` unset.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence

from chalk.models import Week


def number_meetings(week_numbers: Sequence[int | None]) -> list[int | None]:
    """Each schedule row's meeting within its week, from the rows' week
    numbers in order (None for a break row, which stays None). All None
    when no week has more than one row."""
    counts = Counter(number for number in week_numbers if number is not None)
    if all(count == 1 for count in counts.values()):
        return [None] * len(week_numbers)
    seen: Counter = Counter()
    meetings: list[int | None] = []
    for number in week_numbers:
        if number is None:
            meetings.append(None)
            continue
        seen[number] += 1
        meetings.append(seen[number])
    return meetings


def with_meetings(weeks: list[Week]) -> list[Week]:
    """`weeks` with each row's `meeting` filled in (see number_meetings)."""
    meetings = number_meetings([None if week.is_break else week.week_number for week in weeks])
    return [week.model_copy(update={"meeting": meeting}) for week, meeting in zip(weeks, meetings)]


def week_count(weeks: Iterable[Week]) -> int:
    """How many teaching weeks the schedule has (breaks aside), however
    many rows each week has."""
    return len({week.week_number for week in weeks if not week.is_break})


def week_key(week) -> tuple[int | None, int | None]:
    """A schedule row's identity: its week and its meeting in that week.
    Takes a Week or a rollover WeekChange."""
    return week.week_number, week.meeting
