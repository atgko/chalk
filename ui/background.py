"""Long operations (AI generation, reading a syllabus, a rollover preview)
on a background thread, so switching tabs doesn't stop them.

The tabs rerun the app when the instructor switches tabs (shell.py), and
a rerun stops whatever the previous run was doing, including a paid AI
call partway through (sponsor meeting, Oct 15). A job started here keeps
running across reruns: its Future lives in session state, the shell's
status line polls it, and the view that started it picks up the result
on the next run, whichever tab is showing.

Jobs must not call Streamlit: they run outside the script thread, so
they get plain arguments and return a value (or raise) for the view to
apply.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass

import streamlit as st

_JOBS_KEY = "chalk_background_jobs"
_ANNOUNCED_KEY = "chalk_background_announced"
POLL_SECONDS = 1


@dataclass(frozen=True)
class Job:
    label: str
    future: Future
    started_at: float


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
    """Finished jobs the status line has already rerun the app for."""
    return st.session_state.setdefault(_ANNOUNCED_KEY, set())


def start(name: str, label: str, fn: Callable, *args, **kwargs) -> None:
    """Start job `name` unless one by that name is already running.
    `label` is what the status line shows, e.g. "Generating a quiz"."""
    if is_running(name):
        return
    _announced().discard(name)
    _jobs()[name] = Job(label, _submit(fn, *args, **kwargs), time.monotonic())


def is_running(name: str) -> bool:
    job = _jobs().get(name)
    return job is not None and not job.future.done()


def take_finished(name: str) -> Future | None:
    """The finished job `name`, removed so its result is applied once;
    None while it's still running or if there's no such job."""
    job = _jobs().get(name)
    if job is None or not job.future.done():
        return None
    del _jobs()[name]
    return job.future


def render_status() -> None:
    """A status line for each running job, refreshed every second until
    they finish. Drawn above the tabs, so it shows on every tab."""
    if any(not job.future.done() for job in _jobs().values()):
        _status()


@st.fragment(run_every=POLL_SECONDS)
def _status() -> None:
    finished = {name for name, job in _jobs().items() if job.future.done()}
    if finished - _announced():  # rerun the app once, so the job's view applies its result
        _announced().update(finished)
        st.rerun()
    running = [job for job in _jobs().values() if not job.future.done()]
    for job in running:
        elapsed = int(time.monotonic() - job.started_at)
        st.info(
            f"{job.label}… ({elapsed}s). You can keep working on other tabs; "
            "Chalk will show the result when it's ready.",
            icon="⏳",
        )
