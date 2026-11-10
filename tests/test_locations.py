"""Where course projects live (Nov 9 UAT): a "Chalk Courses" folder in
Documents rather than the app's own folder."""

import sys
from pathlib import Path

import pytest

from chalk import locations


def test_projects_go_in_chalk_courses_inside_documents(monkeypatch, tmp_path):
    monkeypatch.delenv(locations.PROJECTS_DIR_ENV, raising=False)
    monkeypatch.setattr(locations, "documents_dir", lambda: tmp_path / "Documents")

    assert locations.default_projects_dir() == tmp_path / "Documents" / "Chalk Courses"


def test_the_projects_folder_can_be_set(monkeypatch, tmp_path):
    monkeypatch.setenv(locations.PROJECTS_DIR_ENV, str(tmp_path / "Shared courses"))

    assert locations.default_projects_dir() == tmp_path / "Shared courses"


def test_documents_falls_back_to_home_when_there_is_no_documents_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(locations.platform, "system", lambda: "Linux")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert locations.documents_dir() == tmp_path
    (tmp_path / "Documents").mkdir()
    assert locations.documents_dir() == tmp_path / "Documents"


@pytest.mark.skipif(sys.platform != "win32", reason="asks Windows for its Documents folder")
def test_windows_reports_a_documents_folder_that_exists():
    assert locations.documents_dir().is_dir()


def test_the_legacy_projects_folder_is_inside_the_app():
    assert locations.LEGACY_PROJECTS_DIR == locations.APP_ROOT / "projects"
    assert (locations.APP_ROOT / "app.py").is_file()


def test_open_in_file_manager_refuses_a_missing_folder(tmp_path):
    assert locations.open_in_file_manager(tmp_path / "missing") is False


def test_open_in_file_manager_opens_the_folder(monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(locations.sys, "platform", "linux")
    monkeypatch.setattr(locations.subprocess, "Popen", lambda command: opened.append(command))

    assert locations.open_in_file_manager(tmp_path) is True
    assert opened == [["xdg-open", str(tmp_path)]]


def test_open_in_file_manager_reports_a_computer_that_cant(monkeypatch, tmp_path):
    def fail(command):
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(locations.sys, "platform", "linux")
    monkeypatch.setattr(locations.subprocess, "Popen", fail)

    assert locations.open_in_file_manager(tmp_path) is False
