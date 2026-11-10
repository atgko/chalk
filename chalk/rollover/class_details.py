"""The class time and location at rollover (Nov 9 UAT).

A class can move days, times, and rooms between terms. On Rollover the
instructor gives the new term's class days and time (starting from the
old ones) and location (starting blank, since rooms are reassigned each
term). Every place the syllabus repeats the old text is then changed,
not just the line extraction read it from: the UAT found the time
changed near the top but not further down.

Only exact repeats of the old text are changed, so nothing is guessed.
Other lines that look like a class day and time ("Tuesdays 5PM – 6PM")
are listed in the preview, for the instructor to check by hand. A blank
new location becomes "TBA", so the syllabus doesn't keep last term's room
by mistake.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from chalk.models import CourseInfo

TBA = "TBA"
_MAX_MENTIONS = 5
_DAY_AND_TIME_RE = re.compile(
    r"\b(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)(?:day)?s?\b.*?\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
    re.IGNORECASE,
)
_OFFICE_HOURS_RE = re.compile(r"office\s+hours?", re.IGNORECASE)


@dataclass(frozen=True)
class TextChange:
    """Every exact `old` in the syllabus becomes `new`. `what` names it in
    messages ("class time", "location")."""

    old: str
    new: str
    what: str


def class_detail_changes(
    course: CourseInfo, new_time: str | None, new_location: str | None
) -> tuple[list[TextChange], list[str]]:
    """The text changes the new class time and location call for, and
    notes for anything Chalk can't change itself. None for either means
    the instructor wasn't asked (e.g. the CLI), so it's left as it was."""
    changes: list[TextChange] = []
    notes: list[str] = []
    if new_time is not None:
        new_time = new_time.strip()
        old_time = course.meeting_pattern.strip()
        if old_time and new_time and new_time != old_time:
            changes.append(TextChange(old_time, new_time, "class time"))
        elif new_time and not old_time:
            notes.append(
                f"Chalk didn't find a class time in the syllabus to change, so add \"{new_time}\" to it by hand."
            )
    if new_location is not None:
        new_location = new_location.strip()
        old_location = course.location.strip()
        if old_location and new_location != old_location:
            changes.append(TextChange(old_location, new_location or TBA, "location"))
        elif new_location and not old_location:
            notes.append(
                f"Chalk didn't find a location in the syllabus to change, so add \"{new_location}\" to it by hand."
            )
    return changes, notes


def updated_course_details(course: CourseInfo, new_time: str | None, new_location: str | None) -> dict:
    """The CourseInfo fields to update for the new term."""
    updates = {}
    if new_time is not None and new_time.strip():
        updates["meeting_pattern"] = new_time.strip()
    if new_location is not None:
        updates["location"] = new_location.strip() or (TBA if course.location.strip() else "")
    return updates


def change_flags(changes: list[TextChange]) -> list[str]:
    return [f"The {change.what} \"{change.old}\" becomes \"{change.new}\" everywhere it appears in the syllabus." for change in changes]


def other_time_mentions(lines: Iterable[str], changes: list[TextChange], course: CourseInfo) -> list[str]:
    """Lines that mention a class day and time but aren't the class time
    Chalk is changing, for the instructor to check. Office hours are left
    out; so are lines holding the old class time (those are changed)."""
    known = [change.old for change in changes if change.what == "class time"] or [course.meeting_pattern.strip()]
    found: list[str] = []
    for line in lines:
        text = " ".join(line.split())
        if not text or any(old and old in text for old in known) or _OFFICE_HOURS_RE.search(text):
            continue
        if _DAY_AND_TIME_RE.search(text) and text not in found:
            found.append(text if len(text) <= 120 else text[:117] + "…")
        if len(found) == _MAX_MENTIONS:
            break
    return found


def mentions_flag(mentions: list[str]) -> str | None:
    if not mentions:
        return None
    quoted = "; ".join(f"\"{text}\"" for text in mentions)
    return f"These lines also mention a day and time. If any is the class time, update it by hand: {quoted}."


# ---- Writing --------------------------------------------------------------------


def replace_in_lines(lines: list[str], changes: list[TextChange]) -> list[str]:
    """Markdown: every exact repeat changed, line by line."""
    for change in changes:
        lines = [line.replace(change.old, change.new) for line in lines]
    return lines


def replace_in_document(document, changes: list[TextChange]) -> int:
    """Word: every exact repeat changed in the body, tables (nested ones
    too), headers, and footers, keeping each run's formatting. Text split
    across runs is joined into the run where it starts. Returns how many
    were changed."""
    count = 0
    for paragraph in _all_paragraphs(document):
        for change in changes:
            count += _replace_in_paragraph(paragraph, change.old, change.new)
    return count


def document_lines(document) -> list[str]:
    return [paragraph.text for paragraph in _all_paragraphs(document)]


def _all_paragraphs(document) -> Iterator:
    yield from _paragraphs_in(document)
    for section in document.sections:
        for part in (section.header, section.footer):
            if not part.is_linked_to_previous:
                yield from _paragraphs_in(part)


def _paragraphs_in(container) -> Iterator:
    yield from container.paragraphs
    for table in container.tables:
        for row in table.rows:
            seen = set()
            for cell in row.cells:
                if id(cell._tc) in seen:  # a merged cell appears once per column it spans
                    continue
                seen.add(id(cell._tc))
                yield from _paragraphs_in(cell)


def _replace_in_paragraph(paragraph, old: str, new: str) -> int:
    count = 0
    search_from = 0
    while True:
        runs = paragraph.runs
        texts = [run.text for run in runs]
        start = "".join(texts).find(old, search_from)
        if start < 0 or not old:
            return count
        end = start + len(old)
        position = 0
        placed = False
        for run, text in zip(runs, texts, strict=True):
            run_start, run_end = position, position + len(text)
            position = run_end
            if run_end <= start or run_start >= end:
                continue
            keep_before = text[: max(start - run_start, 0)]
            keep_after = text[max(end - run_start, 0) :] if run_end > end else ""
            run.text = keep_before + ("" if placed else new) + keep_after
            placed = True
        count += 1
        search_from = start + len(new)
