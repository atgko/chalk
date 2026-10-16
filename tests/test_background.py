"""Background jobs (ui/background.py) on real threads: a long operation
keeps running when the instructor switches tabs, and its result (or
error) shows once it finishes. test_app.py runs jobs inline instead."""

import threading

import pytest

from tests.test_app import click, launch, texts
from ui import background, session

pytestmark = pytest.mark.usefixtures("isolated_env")

_WAIT_SECONDS = 30


def _job(at, name: str):
    return at.session_state[background._JOBS_KEY][name]


def _wait_for(at, name: str) -> None:
    """Wait until job `name` has finished, if it hasn't been applied yet."""
    job = at.session_state[background._JOBS_KEY].get(name)
    if job is not None:
        job.future.exception(timeout=_WAIT_SECONDS)


def _run_on_tab(at, tab: str):
    """Rerun with `tab` showing. The browser sends the open tab on every
    run; AppTest doesn't keep it, so set it each time."""
    at.session_state[session.ACTIVE_TAB_KEY] = tab
    return at.run()


def _blocked_llm(monkeypatch, *, fail: bool = False) -> threading.Event:
    """An AI provider that answers (or fails) only once the test releases it."""
    from chalk.errors import LLMProviderError

    release = threading.Event()

    def _complete(prompt, system="", max_tokens=2000):
        release.wait(_WAIT_SECONDS)
        if fail:
            raise LLMProviderError("Could not reach the LLM provider. Check your connection.")
        return {
            "text": "## Questions\nQ1. A background draft",
            "input_tokens": 1000,
            "output_tokens": 500,
        }

    monkeypatch.setattr("chalk.generation.engine.complete", _complete)
    return release


def test_generation_keeps_running_across_a_tab_switch(saved_project, monkeypatch):
    release = _blocked_llm(monkeypatch)
    at = launch(saved_project, **{session.ACTIVE_TAB_KEY: "Generate"})
    at = click(at, "Generate")

    assert "Generating your draft. It will appear here when it's ready." in texts(at.info)
    assert any(t.startswith("Generating a draft (Quiz, Week 1)… (") for t in texts(at.info))

    at = _run_on_tab(at, "Drafts")  # the instructor moves on
    assert not at.exception
    assert not _job(at, "generate").future.done()

    release.set()
    _wait_for(at, "generate")
    at = _run_on_tab(at, "Drafts")

    assert not at.exception
    assert "Your draft (Quiz, Week 1) is ready on the Generate tab." in texts(at.success)
    assert at.session_state[session.ACTIVE_TAB_KEY] == "Drafts"  # not pulled back to Generate
    assert "Save" in {b.label for b in at.button}


def test_a_generation_that_fails_on_another_tab_is_reported_there(saved_project, monkeypatch):
    release = _blocked_llm(monkeypatch, fail=True)
    at = click(launch(saved_project, **{session.ACTIVE_TAB_KEY: "Generate"}), "Generate")
    at = _run_on_tab(at, "Metrics")

    release.set()
    _wait_for(at, "generate")
    at = _run_on_tab(at, "Metrics")

    assert any(
        e.startswith("Generation failed: Could not reach the LLM provider") for e in texts(at.error)
    )
    assert "Generate" in {b.label for b in at.button}  # the form is back


def test_a_finished_job_is_applied_once(saved_project, monkeypatch):
    release = _blocked_llm(monkeypatch)
    release.set()
    at = click(launch(saved_project, **{session.ACTIVE_TAB_KEY: "Generate"}), "Generate")
    _wait_for(at, "generate")
    at = at.run()
    assert "Save" in {b.label for b in at.button}
    assert at.session_state[background._JOBS_KEY] == {}

    at = click(at, "Discard")  # applying it again would bring the discarded draft back
    assert "Save" not in {b.label for b in at.run().button}


def test_submit_hands_back_the_result_or_the_error():
    assert background._submit(lambda x: x * 2, 21).result(timeout=_WAIT_SECONDS) == 42

    def _boom():
        raise ValueError("nope")

    error = background._submit(_boom).exception(timeout=_WAIT_SECONDS)
    assert isinstance(error, ValueError)


# ---- A syllabus read in the background ----------------------------------------------


def _finished_extraction(project, tmp_path) -> dict:
    """Session state holding a finished extraction job, as the Upload tab's
    Extract button leaves it (AppTest can't drive a file upload)."""
    from concurrent.futures import Future

    from tests.fixtures import md_builder
    from ui.upload_view import extract_upload

    future: Future = Future()
    future.set_result(
        extract_upload(project, md_builder.build_minimal_syllabus(tmp_path / "syllabus.md"))
    )
    return {background._JOBS_KEY: {"extract": background.Job("Reading syllabus.md", future, 0.0)}}


def test_an_extraction_finished_on_the_upload_tab_opens_review(project, tmp_path):
    at = launch(
        project, **_finished_extraction(project, tmp_path), **{session.ACTIVE_TAB_KEY: "Upload"}
    )

    assert not at.exception
    assert at.session_state[session.ACTIVE_TAB_KEY] == "Review"
    assert at.session_state["chalk_pending_extraction"] is not None


def test_an_extraction_finished_on_another_tab_leaves_the_instructor_there(project, tmp_path):
    at = launch(
        project, **_finished_extraction(project, tmp_path), **{session.ACTIVE_TAB_KEY: "Settings"}
    )

    assert not at.exception
    assert at.session_state[session.ACTIVE_TAB_KEY] == "Settings"
    assert any(s.endswith("Check it on the Review tab.") for s in texts(at.success))
