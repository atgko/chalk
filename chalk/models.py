"""Pydantic schema for course.json — the structured source of truth every
Chalk feature reads from and (after Review-tab confirmation) writes to.
See PRD section 5.2 for the canonical JSON shape and DECISIONS.md for why
this is typed pydantic models rather than raw dicts validated against a
JSON Schema document.
"""

from __future__ import annotations

# Imported as a module (not `from datetime import date, datetime`) because
# several models below have a *field* named `date` — with the bare class
# imported, resolving the `date | None` forward-ref annotation on that same
# model looks up `date` in a namespace where the field's own default value
# has already shadowed the class name, and blows up at collection time.
import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CourseInfo(BaseModel):
    title: str
    number: str
    section: str
    credits: int
    term: str
    term_start: dt.date
    term_end: dt.date
    duration_weeks: int = Field(gt=0)
    meeting_pattern: str
    instructor: str
    source_format: Literal["word", "markdown"]
    source_file: str
    extracted_at: dt.datetime


class Assessment(BaseModel):
    name: str
    weight: float = Field(ge=0, le=1)


class Week(BaseModel):
    """A single instructional week, or a break period.

    Regular weeks carry `week_number` and `date`. Break periods (is_break
    True) carry `date_start`/`date_end` instead and leave `week_number`
    unset, matching PRD section 5.2's Fall Break example.
    """

    week_number: int | None = None
    date: dt.date | None = None
    date_start: dt.date | None = None
    date_end: dt.date | None = None
    label: str
    is_break: bool = False
    topics: list[str] = Field(default_factory=list)
    assignments: list[str] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def _require_fields_for_week_kind(self) -> "Week":
        if self.is_break:
            if self.date_start is None or self.date_end is None:
                raise ValueError("A break week must have date_start and date_end.")
        else:
            if self.week_number is None or self.date is None:
                raise ValueError("A non-break week must have week_number and date.")
        return self


class UniversityDate(BaseModel):
    event: str
    date: dt.date | None = None
    date_start: dt.date | None = None
    date_end: dt.date | None = None

    @model_validator(mode="after")
    def _require_date_or_range(self) -> "UniversityDate":
        has_single_date = self.date is not None
        has_date_range = self.date_start is not None and self.date_end is not None
        if not (has_single_date or has_date_range):
            raise ValueError(
                "A university date must have either 'date' or both "
                "'date_start' and 'date_end'."
            )
        return self


class SourceMaterialRef(BaseModel):
    filename: str
    added_at: dt.datetime


class CourseData(BaseModel):
    """The full contents of course.json — the source of truth every other
    Chalk feature (rollover, Canvas export, course brief, generation) reads
    from."""

    course: CourseInfo
    learning_objectives: list[str] = Field(default_factory=list)
    assessments: list[Assessment] = Field(default_factory=list)
    weeks: list[Week] = Field(default_factory=list)
    university_dates: list[UniversityDate] = Field(default_factory=list)
    source_materials: list[SourceMaterialRef] = Field(default_factory=list)
