"""The launch screen's Browse… helper (ui.folder_picker). The real dialog
needs a person to click it, so these replace the subprocess that shows it."""

import subprocess
from pathlib import Path

from ui import folder_picker


def _fake_run(stdout: str = "", error: Exception | None = None, calls: list | None = None):
    def run(args, **kwargs):
        if calls is not None:
            calls.append(args)
        if error is not None:
            raise error
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    return run


def test_returns_the_chosen_folder_in_this_systems_style(monkeypatch):
    monkeypatch.setattr(folder_picker.subprocess, "run", _fake_run("C:/courses/IS-6640\n"))

    assert folder_picker.pick_folder("", "Choose a folder") == str(Path("C:/courses/IS-6640"))


def test_returns_none_when_the_dialog_is_cancelled(monkeypatch):
    monkeypatch.setattr(folder_picker.subprocess, "run", _fake_run(""))

    assert folder_picker.pick_folder("", "Choose a folder") is None


def test_returns_none_when_the_dialog_cant_start(monkeypatch):
    monkeypatch.setattr(folder_picker.subprocess, "run", _fake_run(error=OSError("no display")))

    assert folder_picker.pick_folder("", "Choose a folder") is None


def test_returns_none_when_the_dialog_process_fails(monkeypatch):
    failure = subprocess.CalledProcessError(1, "python", stderr="TclError: no display")
    monkeypatch.setattr(folder_picker.subprocess, "run", _fake_run(error=failure))

    assert folder_picker.pick_folder("", "Choose a folder") is None


def test_starts_in_the_given_folder_with_the_given_title(monkeypatch):
    calls: list = []
    monkeypatch.setattr(folder_picker.subprocess, "run", _fake_run("", calls=calls))

    folder_picker.pick_folder("C:/courses", "Choose where to create the project")

    assert calls[0][-2:] == ["C:/courses", "Choose where to create the project"]


def test_is_available_matches_whether_tkinter_can_be_found(monkeypatch):
    monkeypatch.setattr(folder_picker.importlib.util, "find_spec", lambda name: None)
    assert not folder_picker.is_available()

    monkeypatch.setattr(folder_picker.importlib.util, "find_spec", lambda name: object())
    assert folder_picker.is_available()
