"""Progress reports from long operations, for the app's progress bar
(sponsor meeting, Oct 15: show how far along the work really is, not a
bar that fills on a timer).

A long operation takes an optional `on_progress` callback and calls it
with `(fraction, step)`: `fraction` is 0-1 when Chalk can measure how far
along it is, or None when it can only say which step it's on; `step` is a
short description such as "The AI is writing". The CLI and tests pass no
callback, so every report is optional.

An AI call is one request, so its progress is measured by the reply
streaming in: the text received so far against the reply length Chalk
expects (`writing_progress`).
"""

from __future__ import annotations

from collections.abc import Callable

ProgressCallback = Callable[[float | None, str], None]
TextCallback = Callable[[int], None]

# A rough, widely used average for English text; good enough for a bar.
CHARS_PER_TOKEN = 4
# Never show a step as finished before it is: the reply may run longer
# than expected, so the bar waits just short of full until it ends.
_MAX_UNFINISHED = 0.97

WRITING_STEP = "The AI is writing"


def report(on_progress: ProgressCallback | None, fraction: float | None, step: str) -> None:
    """Pass a report on, if anyone asked for progress."""
    if on_progress is not None:
        on_progress(fraction, step)


def within(on_progress: ProgressCallback | None, start: float, end: float) -> ProgressCallback | None:
    """A callback for one part of a longer operation: its 0-1 progress
    fills the stretch from `start` to `end` of the whole bar."""
    if on_progress is None:
        return None

    def scaled(fraction: float | None, step: str) -> None:
        on_progress(None if fraction is None else start + (end - start) * fraction, step)

    return scaled


def writing_progress(on_progress: ProgressCallback | None, expected_tokens: int) -> TextCallback | None:
    """A callback for `complete(on_text=...)` that turns the length of the
    reply so far into progress against the reply length expected."""
    if on_progress is None:
        return None
    expected_chars = max(expected_tokens, 1) * CHARS_PER_TOKEN

    def on_text(chars_so_far: int) -> None:
        on_progress(min(chars_so_far / expected_chars, _MAX_UNFINISHED), WRITING_STEP)

    return on_text
