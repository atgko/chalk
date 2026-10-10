"""The system folder dialog behind the launch screen's Browse… buttons.

Chalk runs on the instructor's own computer, so the dialog can come from
the Python side. It runs in a separate Python process: Streamlit runs
page code on a worker thread, and Tk (especially on macOS) must own its
process's main thread.

The dialog is started, not waited for: the page keeps running and polls
`finished()`, so a dialog left open (or hidden behind the browser) never
freezes the app.
"""

from __future__ import annotations

import importlib.util
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# argv: initial folder ("" for the system default), dialog title.
# Prints the chosen folder, or nothing if the dialog is cancelled.
# Windows won't let a background process take the foreground, so the
# dialog gets a real (invisible, 1-pixel) always-on-top parent window:
# windows owned by a topmost window stay above the browser, and the
# parent's taskbar button is a way back to the dialog.
_DIALOG_SCRIPT = """
import sys
import tkinter
from tkinter import filedialog

root = tkinter.Tk()
root.title(sys.argv[2])
root.attributes("-alpha", 0.0)
root.geometry("1x1+200+200")
root.attributes("-topmost", True)
root.lift()
root.focus_force()
root.update()
print(filedialog.askdirectory(parent=root, initialdir=sys.argv[1] or None, title=sys.argv[2], mustexist=True) or "")
"""


def is_available() -> bool:
    """Whether this Python can show the dialog (some builds lack Tk)."""
    return importlib.util.find_spec("tkinter") is not None


def start(initial: str, title: str) -> subprocess.Popen | None:
    """Open the dialog without waiting for it. None if it couldn't start."""
    try:
        return subprocess.Popen(
            [sys.executable, "-c", _DIALOG_SCRIPT, initial, title],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        logger.warning("Folder dialog couldn't start: %s", exc)
        return None


def finished(process: subprocess.Popen) -> bool:
    return process.poll() is not None


def chosen_folder(process: subprocess.Popen) -> str | None:
    """The folder picked in a finished dialog, or None if it was
    cancelled or failed."""
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        logger.warning("Folder dialog failed: %s", stderr)
        return None
    chosen = stdout.strip()
    return str(Path(chosen)) if chosen else None


def cancel(process: subprocess.Popen) -> None:
    """Close a dialog that's still open."""
    if not finished(process):
        process.terminate()
    process.communicate()
