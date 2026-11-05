"""Long operations (AI generation, reading a syllabus, a rollover preview)
on a background thread, so switching tabs doesn't stop them.

The tabs rerun the app when the instructor switches tabs (shell.py), and
a rerun stops whatever the previous run was doing, including a paid AI
call partway through (sponsor meeting, Oct 15). A job started here keeps
running across reruns: its Future lives in session state, and the view
that started it picks up the result on the next run, whichever tab is
showing.

Jobs must not call Streamlit: they run outside the script thread, so
they get plain arguments and return a value (or raise) for the view to
apply. Each job is also given an `on_progress` callback
(chalk/progress.py), which `render_progress` shows inside the job's tab.

Every job belongs to a tab, and the tab's label shows how it's going
(`render_tab_marks`): a spinner and amber text while it runs, then a
green check (or a red cross if it failed) until the instructor opens
that tab. A job that finishes on another tab also pops up a toast. UAT
of PR #18: a status line drawn above the tabs shifted the page and left
a second row of tabs behind, so nothing here takes up page space
outside the job's own tab.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Literal

import streamlit as st

from ui import session

_JOBS_KEY = "chalk_background_jobs"
_ANNOUNCED_KEY = "chalk_background_announced"
_MARKS_KEY = "chalk_tab_marks"
_TOASTS_KEY = "chalk_toasts"
_ERRORS_KEY = "chalk_tab_errors"
POLL_SECONDS = 1

TabMark = Literal["running", "done", "failed"]


class Progress:
    """A job's latest progress report. The job's thread writes it and the
    view reads it, hence the lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fraction: float | None = None
        self._step = ""

    def update(self, fraction: float | None, step: str) -> None:
        with self._lock:
            self._fraction, self._step = fraction, step

    def latest(self) -> tuple[float | None, str]:
        with self._lock:
            return self._fraction, self._step


@dataclass(frozen=True)
class Job:
    """A running or finished job, kept in session state under its name.
    `tab` is the tab that started it, whose label shows its status."""
    label: str
    future: Future
    started_at: float
    progress: Progress = field(default_factory=Progress)
    tab: str = ""


def _submit(fn: Callable, *args, **kwargs) -> Future:
    """Run `fn` on a daemon thread, so a hung network call never keeps
    the app from exiting. Tests replace this to run jobs inline."""
    future: Future = Future()

    def work() -> None:
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - handed to the view, which reports it
            future.set_exception(exc)

    threading.Thread(target=work, daemon=True).start()
    return future


def _jobs() -> dict[str, Job]:
    return st.session_state.setdefault(_JOBS_KEY, {})


def _announced() -> set[str]:
    """Finished jobs the app has already rerun for."""
    return st.session_state.setdefault(_ANNOUNCED_KEY, set())


def _marks() -> dict[str, TabMark]:
    """Finished jobs' marks ("done"/"failed"), by tab, until it's opened."""
    return st.session_state.setdefault(_MARKS_KEY, {})


def start(name: str, label: str, fn: Callable, *args, tab: str, **kwargs) -> None:
    """Start `fn(*args, **kwargs, on_progress=...)` as job `name` for tab
    `tab`, unless one by that name is already running. `label` is what
    the progress line shows, e.g. "Generating a draft (Quiz, Week 3)"."""
    if is_running(name):
        return
    _announced().discard(name)
    _marks().pop(tab, None)
    progress = Progress()
    future = _submit(fn, *args, **kwargs, on_progress=progress.update)
    _jobs()[name] = Job(label, future, time.monotonic(), progress, tab)


def is_running(name: str) -> bool:
    job = _jobs().get(name)
    return job is not None and not job.future.done()


def any_running() -> bool:
    return any(not job.future.done() for job in _jobs().values())


def take_finished(name: str) -> Future | None:
    """The finished job `name`, removed so its result is applied once;
    None while it's still running or if there's no such job."""
    job = _jobs().get(name)
    if job is None or not job.future.done():
        return None
    del _jobs()[name]
    return job.future


# ---- Telling the instructor a job finished ---------------------------------------


def finished_elsewhere(tab: str, message: str, *, failed: bool = False) -> None:
    """A job for `tab` finished while the instructor was on another tab:
    mark the tab (check or cross), queue a toast, and keep a failure's
    message to show on the tab when they open it."""
    _marks()[tab] = "failed" if failed else "done"
    st.session_state.setdefault(_TOASTS_KEY, []).append((message, failed))
    if failed:
        st.session_state.setdefault(_ERRORS_KEY, {})[tab] = message


def show_toasts() -> None:
    """Pop up the queued toasts. Toasts float in a corner, so they never
    move the page."""
    for message, failed in st.session_state.pop(_TOASTS_KEY, []):
        st.toast(message, icon="⚠️" if failed else "✅")


def clear_mark(tab: str) -> None:
    """The instructor opened `tab`: its label goes back to normal."""
    _marks().pop(tab, None)


def pop_error(tab: str) -> str | None:
    """A failure kept for `tab`, once, when `tab` is the open tab (every
    tab's content is drawn on every run, the hidden ones too)."""
    if session.active_tab() != tab:
        return None
    return st.session_state.get(_ERRORS_KEY, {}).pop(tab, None)


def tab_marks() -> dict[str, TabMark]:
    """Each marked tab's status: running jobs, then finished-but-unseen."""
    marks: dict[str, TabMark] = dict(_marks())
    for job in _jobs().values():
        if not job.future.done():
            marks[job.tab] = "running"
    return marks


# ---- Drawing --------------------------------------------------------------------


def render_tab_marks(
    groups: dict[str, tuple[str, ...]],
    group_key: str,
    sub_keys: dict[str, str],
    *,
    inactive: Iterable[str] = (),
) -> None:
    """Style the tab labels: running, done, failed, or inactive (a tab
    that can't be used yet), in both rows of tabs. A group's label shows
    the most pressing mark among its tabs. While a job runs this refreshes
    every second, and reruns the app once a job finishes so its view
    applies the result. Draw it after the tabs, so it never moves them."""
    layout = (tuple(groups.items()), group_key, tuple(sub_keys.items()))
    if any_running():
        _polled_marks(layout, tuple(inactive))
    else:
        _draw_marks(layout, tuple(inactive))


@st.fragment(run_every=POLL_SECONDS)
def _polled_marks(layout: tuple, inactive: tuple[str, ...]) -> None:
    _rerun_if_a_job_finished()
    _draw_marks(layout, inactive)


def _draw_marks(layout: tuple, inactive: tuple[str, ...]) -> None:
    groups, group_key, sub_keys = dict(layout[0]), layout[1], dict(layout[2])
    marks = tab_marks()
    group_marks = {group: _strongest([marks.get(tab) for tab in tabs]) for group, tabs in groups.items()}
    css = [tab_marks_css(tuple(groups), group_key, group_marks, nested_keys=tuple(sub_keys.values()))]
    css += [tab_marks_css(groups[group], key, marks, inactive) for group, key in sub_keys.items()]
    st.html("<style>" + "\n".join(css) + "</style>")


def _strongest(marks: list) -> TabMark | None:
    """The mark a group shows for its tabs: running, then failed, then done."""
    return next((mark for mark in ("running", "failed", "done") if mark in marks), None)


def _rerun_if_a_job_finished() -> None:
    finished = {name for name, job in _jobs().items() if job.future.done()}
    if finished - _announced():
        _announced().update(finished)
        st.rerun()


def render_progress(name: str) -> None:
    """Job `name`'s progress, inside its own tab: a bar once there's a
    fraction to show, else the current step. Refreshes every second."""
    if is_running(name):
        _progress(name)


@st.fragment(run_every=POLL_SECONDS)
def _progress(name: str) -> None:
    _rerun_if_a_job_finished()
    job = _jobs().get(name)
    if job is None or job.future.done():
        return
    fraction, step = job.progress.latest()
    elapsed = int(time.monotonic() - job.started_at)
    status = f"{job.label}: {step}" if step else job.label
    if fraction is None:
        st.info(f"{status}… ({elapsed}s)", icon="⏳")
    else:
        st.progress(fraction, text=f"{status}… {round(fraction * 100)}% ({elapsed}s)")
    st.caption(_KEEP_WORKING)


_KEEP_WORKING = "You can keep working on other tabs; this tab's label shows a check mark when it's done."


# ---- The CSS ----------------------------------------------------------------------

# Text colors from .streamlit/config.toml (orange/green/red TextColor),
# each checked against its theme's background for WCAG AA.
_COLORS = {
    "light": {"running": "#7A4F00", "done": "#2E6A1C", "failed": "#890000"},
    "dark": {"running": "#FFCF66", "done": "#9BDC7F", "failed": "#FF9A8F"},
}
_SYMBOLS = {"done": "✓", "failed": "✕"}


def tab_marks_css(
    tab_names: tuple[str, ...],
    tabs_key: str,
    marks: dict[str, TabMark],
    inactive: tuple[str, ...] = (),
    *,
    nested_keys: tuple[str, ...] = (),
) -> str:
    """The CSS for the tab labels. Streamlit gives the tabs widget a
    `st-key-<key>` class and each label `data-testid="stTab"`; a label is
    picked by its position. `nested_keys` are tabs widgets inside this
    one, whose labels these rules must skip. A status uses both a color
    and a symbol, so it doesn't rely on color alone."""
    rules = [_SPINNER_KEYFRAMES]
    light, dark = [], []
    skip = "".join(f":not(.st-key-{key} *)" for key in nested_keys)
    for position, name in enumerate(tab_names, start=1):
        tab = f'.st-key-{tabs_key} [data-testid="stTab"]:nth-of-type({position}){skip}'
        mark = marks.get(name)
        if mark == "running":
            rules.append(f"{tab}::before {{{_SPINNER}}}")
        elif mark in _SYMBOLS:
            rules.append(f'{tab}::before {{content: "{_SYMBOLS[mark]}"; margin-right: 0.35em; font-weight: 700;}}')
        elif name in inactive:
            rules.append(f"{tab} {{opacity: 0.45;}}")
        if mark:
            light.append(f"{tab}, {tab} p {{color: {_COLORS['light'][mark]};}}")
            dark.append(f"{tab}, {tab} p {{color: {_COLORS['dark'][mark]};}}")
    rules += light
    if dark:
        rules.append(f"@media (prefers-color-scheme: dark) {{{' '.join(dark)}}}")
    return "\n".join(rules)


_SPINNER_KEYFRAMES = (
    "@keyframes chalk-spin {to {transform: rotate(360deg);}}\n"
    "@media (prefers-reduced-motion: reduce) {[data-testid=\"stTab\"]::before {animation: none !important;}}"
)
_SPINNER = (
    'content: ""; display: inline-block; width: 0.75em; height: 0.75em; margin-right: 0.4em; '
    "border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; "
    "vertical-align: -0.1em; animation: chalk-spin 0.9s linear infinite;"
)
