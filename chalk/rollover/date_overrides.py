"""The instructor's own dates at rollover (Nov 9 UAT: "users should be
able to override the generation dates if they don't match").

The preview's dates come from the calendar and the class days picked.
When one is wrong for this class (a make-up week, a class that starts a
week late), the instructor types the right date in the preview table, and
that date is what the rolled-over syllabus says. Only class weeks can be
changed this way; break rows follow the calendar.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

from chalk.models import CourseData, Week
from chalk.rollover.preview import RolloverPreview, WeekChange


def override_week_dates(
    rolled_over: CourseData, preview: RolloverPreview, new_dates: list[dt.date | None]
) -> tuple[CourseData, RolloverPreview]:
    """Apply the instructor's dates, `new_dates` being one per preview row
    in order (None or the computed date: unchanged). Returns the course and
    preview with each changed week's date and label updated, and a note
    naming the weeks changed. Raises ValueError if the counts differ."""
    if len(new_dates) != len(preview.week_changes):
        raise ValueError("One date is needed per row of the rollover preview.")
    weeks = list(rolled_over.weeks)
    changes = list(preview.week_changes)
    changed_names = []
    for index, (change, new_date) in enumerate(zip(changes, new_dates, strict=True)):
        if change.week_number is None or new_date is None or new_date == change.new_date:
            continue
        position = _find_week(weeks, change)
        label = f"Week {change.week_number} ({new_date.month}/{new_date.day})"
        weeks[position] = weeks[position].model_copy(update={"date": new_date, "label": label})
        changes[index] = dataclasses.replace(change, new_date=new_date, label=label)
        changed_names.append(f"Week {change.week_number}")
    if not changed_names:
        return rolled_over, preview
    weeks.sort(key=_sort_key)
    last = weeks[-1]
    course = rolled_over.course.model_copy(update={"term_end": last.date if last.date else last.date_end})
    note = (
        f"You changed the date of {', '.join(changed_names)}. Holiday and break warnings were worked "
        "out for the calendar's dates, so check the changed weeks against the calendar."
    )
    return (
        rolled_over.model_copy(update={"weeks": weeks, "course": course}),
        dataclasses.replace(preview, week_changes=changes, general_flags=[*preview.general_flags, note]),
    )


def _find_week(weeks: list[Week], change: WeekChange) -> int:
    for position, week in enumerate(weeks):
        if (
            not week.is_break
            and week.week_number == change.week_number
            and week.meeting == change.meeting
            and week.date == change.new_date
        ):
            return position
    raise ValueError(f"Week {change.week_number} isn't in the rolled-over schedule.")


def _sort_key(week: Week) -> dt.date:
    return week.date if week.date is not None else week.date_start
