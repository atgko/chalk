"""Custom exception hierarchy for Chalk.

Every exception here carries a `user_message` attribute holding the
plain-English text to show directly in a UI callout or CLI line, matching
PRD section 7.3's error-message table where a row exists for it. Python
tracebacks must never reach the instructor (PRD section 2, "Fails loudly,
never silently") — callers catch `ChalkError` (or a specific subclass) and
render `.user_message`, never a raw `str(exc)` on anything else.
"""

from __future__ import annotations


class ChalkError(Exception):
    """Base class for every exception Chalk raises intentionally."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


class LLMProviderError(ChalkError):
    """Raised when an LLM provider call fails, for any reason.

    This is the only exception type that may escape chalk.llm_client —
    every caller wraps LLM calls in a try/except for this one type
    (PRD section 4.1).
    """


class ExtractionError(ChalkError):
    """Raised when a syllabus cannot be parsed into a CourseData object."""


class AmbiguousTableError(ExtractionError):
    """Raised when zero or multiple candidate schedule tables are found.

    `candidates` holds a short text preview per candidate table (e.g. the
    first row's text) so the UI can render a manual-override picker
    (DECISIONS.md, "Word table detection") when there's more than one to
    choose from. An empty list means no candidate matched at all — a dead
    end the instructor resolves by reformatting the document, not by
    picking from a list.
    """

    def __init__(self, user_message: str, candidates: list[str]):
        super().__init__(user_message)
        self.candidates = candidates


class ProtectedFileError(ExtractionError):
    """Raised when a Word file can't be opened — typically because it is
    password-protected, occasionally because it is otherwise corrupt in a
    way python-docx cannot open (DECISIONS.md: caught via exception, no
    zip pre-check)."""


class ProjectError(ChalkError):
    """Raised for course-project problems the instructor fixes by pointing
    at a different folder or file: not a Chalk project, a project name
    that already exists, an unsupported source-material file type, or no
    course.json yet."""


class PromptTemplateError(ChalkError):
    """A prompt template is unreadable or missing a required {variable}
    (DECISIONS.md: name the variable and file; never auto-repair)."""


class GenerationError(ChalkError):
    """A generation request can't be run as asked — e.g. an unknown week,
    a rubric with no assignment description, or an unknown source file."""


class TermNotInCalendarError(ChalkError):
    """Raised when a rollover target term isn't in calendars.json and no
    manual Week 1 date was given. Not a dead end — the caller asks for the
    first day of classes and retries (PRD section 5.3)."""

    def __init__(self):
        super().__init__(
            "That term isn't in the calendar data yet. Enter the first day of "
            "classes below and we'll calculate the rest."
        )

