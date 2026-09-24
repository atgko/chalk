"""Tests for chalk.launcher — everything except actually spawning
processes, which is injected."""

import subprocess
import sys

import pytest

from chalk import launcher


def test_python_version_check():
    assert launcher.python_version_problem((3, 11, 0)) is None
    assert launcher.python_version_problem((3, 14, 2)) is None
    message = launcher.python_version_problem((3, 10, 12))
    assert "needs Python 3.11 or newer, but found 3.10.12" in message
    assert "python.org" in message


def test_install_is_needed_until_the_stamp_matches_requirements(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("streamlit>=1.64\n", encoding="utf-8")
    stamp = tmp_path / "stamp"
    calls = []

    assert launcher.needs_install(stamp, requirements)
    launcher.install_requirements(stamp, requirements, run=calls.append)
    assert not launcher.needs_install(stamp, requirements)
    assert calls[0][:4] == [sys.executable, "-m", "pip", "install"]
    assert calls[0][-1] == str(requirements)

    requirements.write_text("streamlit>=1.64\npandas>=3\n", encoding="utf-8")
    assert launcher.needs_install(stamp, requirements)


def test_find_free_port_skips_ports_in_use():
    import socket

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        taken = busy.getsockname()[1]
        assert launcher.find_free_port(taken, attempts=5) != taken


def test_find_free_port_gives_up_eventually(monkeypatch):
    class _AlwaysBusy:
        def __init__(self, *args): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def bind(self, address): raise OSError("in use")

    monkeypatch.setattr(launcher.socket, "socket", _AlwaysBusy)
    with pytest.raises(RuntimeError, match="No free port"):
        launcher.find_free_port(9000, attempts=3)


def test_streamlit_command_is_headless_private_and_passes_the_project(tmp_path):
    command = launcher.streamlit_command(8502, tmp_path / "IS-6640")
    assert command[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert command[4].endswith("app.py")
    for flag, value in (("--server.headless", "true"), ("--server.port", "8502"),
                        ("--server.address", "localhost"), ("--browser.gatherUsageStats", "false")):
        assert command[command.index(flag) + 1] == value
    assert command[-3:] == ["--", "--project", str(tmp_path / "IS-6640")]
    assert "--project" not in launcher.streamlit_command(8501)


def test_wait_until_ready_polls_until_up_or_timeout():
    answers = iter([False, False, True])
    assert launcher.wait_until_ready("u", is_up=lambda url: next(answers), sleep=lambda s: None)

    ticks = iter(range(100))
    assert not launcher.wait_until_ready(
        "u", timeout=3, is_up=lambda url: False, sleep=lambda s: None, clock=lambda: next(ticks)
    )


def test_is_up_is_false_when_nothing_is_listening():
    port = launcher.find_free_port(8700)
    assert not launcher._is_up(f"http://127.0.0.1:{port}/_stcore/health")


# ---- main ----------------------------------------------------------------------------


class _Server:
    def __init__(self, exit_code=0, interrupt=False):
        self.exit_code, self.interrupt, self.terminated = exit_code, interrupt, False

    def wait(self):
        if self.interrupt:
            raise KeyboardInterrupt
        return self.exit_code

    def terminate(self):
        self.terminated = True


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Pretend we're in a venv whose requirements are already installed."""
    monkeypatch.setattr(launcher, "in_virtualenv", lambda: True)
    monkeypatch.setattr(launcher.sys, "prefix", str(tmp_path))
    (tmp_path / launcher.STAMP_NAME).write_text(launcher.requirements_digest(), encoding="utf-8")
    monkeypatch.setattr(launcher, "PROJECTS_DIR", tmp_path / "projects")
    return tmp_path


def _main(*argv, server=None, ready=True, run=None):
    started, opened = [], []
    server = server or _Server()

    def popen(command, cwd):
        started.append((command, cwd))
        return server

    code = launcher.main(
        list(argv), run=run or (lambda cmd: None), popen=popen, open_browser=opened.append,
        ready=lambda url: ready,
    )
    return code, started, opened, server


def test_main_starts_streamlit_and_opens_the_browser(env, capsys):
    code, started, opened, _ = _main()
    assert code == 0
    command, cwd = started[0]
    assert cwd == str(launcher.REPO_ROOT)
    port = command[command.index("--server.port") + 1]
    assert opened == [f"http://localhost:{port}"]
    assert "Keep this window open" in capsys.readouterr().out


def test_main_no_browser(env):
    _, _, opened, _ = _main("--no-browser")
    assert opened == []


def test_main_demo_prepares_and_opens_the_demo_course(env, capsys):
    code, started, _, _ = _main("--demo")
    assert code == 0
    project = env / "projects" / "Chalk-Demo"
    assert (project / "course.json").exists()
    assert started[0][0][-2:] == ["--project", str(project)]
    assert f"Demo course: {project}" in capsys.readouterr().out


def test_main_passes_an_explicit_project(env, tmp_path):
    _, started, _, _ = _main("--project", str(tmp_path / "course"))
    assert started[0][0][-1] == str(tmp_path / "course")


def test_main_installs_requirements_when_they_changed(env, capsys):
    (env / launcher.STAMP_NAME).write_text("stale", encoding="utf-8")
    installs = []
    code, *_ = _main(run=installs.append)
    assert code == 0 and len(installs) == 1
    assert "Installing Chalk's components" in capsys.readouterr().out
    assert not launcher.needs_install(env / launcher.STAMP_NAME)


def test_main_reports_a_failed_install(env, capsys):
    (env / launcher.STAMP_NAME).unlink()

    def fail(cmd):
        raise subprocess.CalledProcessError(1, cmd)

    code, started, *_ = _main(run=fail)
    assert code == 1 and started == []
    assert "Check your internet connection" in capsys.readouterr().out


def test_main_reports_a_server_that_never_comes_up(env, capsys):
    code, _, opened, server = _main(ready=False)
    assert code == 1 and opened == [] and server.terminated
    assert "Chalk didn't start" in capsys.readouterr().out


def test_main_stops_the_server_on_ctrl_c(env):
    code, _, _, server = _main(server=_Server(interrupt=True))
    assert code == 0 and server.terminated


def test_main_refuses_an_old_python(env, monkeypatch, capsys):
    monkeypatch.setattr(launcher, "python_version_problem", lambda: "too old")
    assert _main()[0] == 1
    assert "too old" in capsys.readouterr().out


def test_main_refuses_to_install_outside_a_virtualenv(env, monkeypatch, capsys):
    monkeypatch.setattr(launcher, "in_virtualenv", lambda: False)
    assert _main()[0] == 1
    assert "Start Chalk" in capsys.readouterr().out


def test_in_virtualenv_reflects_the_running_interpreter():
    assert launcher.in_virtualenv() == (sys.prefix != sys.base_prefix)
