"""One-click launcher behind `Start Chalk.bat` / `Start Chalk.command`.

The double-click scripts only create the virtual environment; everything
else happens here, in one cross-platform place:

1. check the Python version
2. install requirements.txt on the first run, and again whenever it changes
3. optionally prepare the demo course
4. start Streamlit on a free port and open the browser once it's ready

Streamlit runs headless so it never stops at its first-run "Email:"
prompt, which would otherwise make a double-clicked launcher look frozen.

Standard library only above the dependency install; chalk modules that
need third-party packages are imported after it.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "requirements.txt"
PROJECTS_DIR = REPO_ROOT / "projects"
MIN_PYTHON = (3, 11)
DEFAULT_PORT = 8501
STAMP_NAME = ".chalk-requirements.sha256"
STARTUP_TIMEOUT_SECONDS = 90

# Progress messages must appear immediately, even when output is redirected.
print = functools.partial(print, flush=True)


def python_version_problem(version: tuple[int, ...] = tuple(sys.version_info[:3])) -> str | None:
    if tuple(version[:2]) >= MIN_PYTHON:
        return None
    found = ".".join(str(part) for part in version[:3])
    return (
        f"Chalk needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer, but found {found}. "
        "Install a newer Python from https://www.python.org/downloads/, delete the .venv folder "
        "next to this launcher, and start Chalk again."
    )


def in_virtualenv() -> bool:
    return sys.prefix != sys.base_prefix


def requirements_digest(requirements: Path = REQUIREMENTS) -> str:
    return hashlib.sha256(requirements.read_bytes()).hexdigest()


def needs_install(stamp: Path, requirements: Path = REQUIREMENTS) -> bool:
    return not stamp.exists() or stamp.read_text(encoding="utf-8").strip() != requirements_digest(requirements)


def install_requirements(stamp: Path, requirements: Path = REQUIREMENTS, *, run: Callable = subprocess.check_call) -> None:
    run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(requirements)])
    stamp.write_text(requirements_digest(requirements), encoding="utf-8")


def find_free_port(start: int = DEFAULT_PORT, attempts: int = 50) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free port found between {start} and {start + attempts - 1}.")


def streamlit_command(port: int, project: Path | None = None) -> list[str]:
    command = [
        sys.executable, "-m", "streamlit", "run", str(REPO_ROOT / "app.py"),
        "--server.headless", "true",
        "--server.port", str(port),
        "--server.address", "localhost",
        "--browser.gatherUsageStats", "false",
    ]
    if project is not None:
        command += ["--", "--project", str(project)]
    return command


def _is_up(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            # Read the body before closing: closing with unread data resets the
            # connection, which Streamlit's server logs as a scary traceback.
            response.read()
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def wait_until_ready(
    url: str,
    *,
    timeout: float = STARTUP_TIMEOUT_SECONDS,
    is_up: Callable[[str], bool] = _is_up,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    deadline = clock() + timeout
    while clock() < deadline:
        if is_up(url):
            return True
        sleep(0.5)
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="Start Chalk", description="Start the Chalk app in your browser.")
    parser.add_argument("--demo", action="store_true", help="Open the demo course.")
    parser.add_argument("--reset-demo", action="store_true", help="Rebuild the demo course first (implies --demo).")
    parser.add_argument("--project", type=Path, help="Open this course project folder.")
    parser.add_argument("--no-browser", action="store_true", help="Don't open a browser window.")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    run: Callable = subprocess.check_call,
    popen: Callable = subprocess.Popen,
    open_browser: Callable[[str], object] = webbrowser.open,
    ready: Callable[[str], bool] = wait_until_ready,
) -> int:
    args = build_parser().parse_args(argv)

    problem = python_version_problem()
    if problem:
        print(problem)
        return 1
    if not in_virtualenv():
        print("Start Chalk with the 'Start Chalk' launcher so it can use its own Python environment.")
        return 1

    stamp = Path(sys.prefix) / STAMP_NAME
    if needs_install(stamp):
        print("Installing Chalk's components. This happens on the first run and after updates, "
              "and takes a minute or two...")
        try:
            install_requirements(stamp, run=run)
        except subprocess.CalledProcessError:
            print("Installing Chalk's components failed. Check your internet connection and try again.")
            return 1

    project = args.project
    if args.demo or args.reset_demo:
        from chalk.demo import open_demo_project

        project = open_demo_project(PROJECTS_DIR, reset=args.reset_demo).root
        print(f"Demo course: {project}")

    port = find_free_port()
    url = f"http://localhost:{port}"
    print("Starting Chalk...")
    server = popen(streamlit_command(port, project), cwd=str(REPO_ROOT))
    if not ready(f"{url}/_stcore/health"):
        print("Chalk didn't start. Scroll up for the error message.")
        server.terminate()
        return 1

    print(f"\nChalk is running at {url}\nKeep this window open while you use Chalk. Close it (or press Ctrl+C) to stop.\n")
    if not args.no_browser:
        open_browser(url)
    try:
        return server.wait()
    except KeyboardInterrupt:
        server.terminate()
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
