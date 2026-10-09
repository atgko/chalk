"""The system folder dialog behind the launch screen's Browse… buttons.

Chalk runs on the instructor's own computer, so the dialog can come from
the Python side. It runs in a separate Python process: Streamlit runs
page code on a worker thread, and Tk (especially on macOS) must own its
process's main thread.
"""

from __future__ import annotations

import importlib.util
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Generous: the instructor may take a while to find the folder.
_DIALOG_TIMEOUT_SECONDS = 600

# argv: initial folder ("" for the system default), dialog title.
# Prints the chosen folder, or nothing if the dialog is cancelled.
_DIALOG_SCRIPT = """
import sys
import tkinter
from tkinter import filedialog

root = tkinter.Tk()
root.withdraw()
root.attributes("-topmost", True)  # in front of the browser
print(filedialog.askdirectory(initialdir=sys.argv[1] or None, title=sys.argv[2], mustexist=True) or "")
"""


def is_available() -> bool:
    """Whether this Python can show the dialog (some builds lack Tk)."""
    return importlib.util.find_spec("tkinter") is not None


def pick_folder(initial: str, title: str) -> str | None:
    """The folder the instructor chose, or None if they cancelled or the
    dialog couldn't be shown."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", _DIALOG_SCRIPT, initial, title],
            capture_output=True,
            text=True,
            timeout=_DIALOG_TIMEOUT_SECONDS,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.warning("Folder dialog failed: %s", exc.stderr)
        return None
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Folder dialog couldn't start: %s", exc)
        return None
    chosen = result.stdout.strip()
    return str(Path(chosen)) if chosen else None
