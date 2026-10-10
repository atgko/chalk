"""The launch screen's Browse… helper (ui.folder_picker). The real dialog
needs a person to click it, so these swap in a script that answers (or
waits) on its own, run in a real child process."""

from pathlib import Path

from ui import folder_picker


def _run(monkeypatch, script: str, initial: str = "", title: str = "Choose a folder"):
    monkeypatch.setattr(folder_picker, "_DIALOG_SCRIPT", script)
    return folder_picker.start(initial, title)


def _wait(process):
    process.wait(timeout=30)
    return process


def test_returns_the_chosen_folder_in_this_systems_style(monkeypatch):
    process = _wait(_run(monkeypatch, "print('C:/courses/IS-6640')"))

    assert folder_picker.finished(process)
    assert folder_picker.chosen_folder(process) == str(Path("C:/courses/IS-6640"))


def test_returns_none_when_the_dialog_is_cancelled(monkeypatch):
    process = _wait(_run(monkeypatch, "print('')"))

    assert folder_picker.chosen_folder(process) is None


def test_returns_none_when_the_dialog_process_fails(monkeypatch):
    process = _wait(_run(monkeypatch, "import sys; sys.exit('TclError: no display')"))

    assert folder_picker.chosen_folder(process) is None


def test_start_returns_none_when_python_cant_be_started(monkeypatch):
    monkeypatch.setattr(folder_picker.sys, "executable", "/no/such/python")

    assert folder_picker.start("", "Choose a folder") is None


def test_passes_the_initial_folder_and_title(monkeypatch):
    process = _wait(_run(monkeypatch, "import sys; print(sys.argv[1] + '|' + sys.argv[2])", "C:/courses", "Pick"))

    assert process.communicate()[0].strip() == "C:/courses|Pick"


def test_an_open_dialog_isnt_finished_until_cancelled(monkeypatch):
    process = _run(monkeypatch, "import time; time.sleep(60)")

    assert not folder_picker.finished(process)
    folder_picker.cancel(process)
    assert folder_picker.finished(process)


def test_is_available_matches_whether_tkinter_can_be_found(monkeypatch):
    monkeypatch.setattr(folder_picker.importlib.util, "find_spec", lambda name: None)
    assert not folder_picker.is_available()

    monkeypatch.setattr(folder_picker.importlib.util, "find_spec", lambda name: object())
    assert folder_picker.is_available()
