"""Where Chalk keeps course projects on this computer.

Projects used to live in a `projects` folder inside the app's own folder,
among its program files, which instructors found hard to find (Nov 9
UAT). New projects now go in a `Chalk Courses` folder in the instructor's
Documents folder, where they look for their files; projects already in
the app folder are still listed, so nothing goes missing.

Windows may move Documents (e.g. into OneDrive), so its real location is
asked from Windows rather than assumed to be ~/Documents.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

PROJECTS_FOLDER_NAME = "Chalk Courses"
PROJECTS_DIR_ENV = "CHALK_PROJECTS_DIR"
APP_ROOT = Path(__file__).resolve().parent.parent
LEGACY_PROJECTS_DIR = APP_ROOT / "projects"


def documents_dir() -> Path:
    """The instructor's Documents folder, or their home folder if there's none."""
    if platform.system() == "Windows":
        known = _windows_documents_dir()
        if known is not None:
            return known
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


def default_projects_dir() -> Path:
    """Where new course projects go: Documents/Chalk Courses, unless the
    CHALK_PROJECTS_DIR setting names another folder."""
    override = os.environ.get(PROJECTS_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return documents_dir() / PROJECTS_FOLDER_NAME


def open_in_file_manager(folder: Path) -> bool:
    """Show `folder` in File Explorer / Finder. False if this computer
    can't (e.g. no desktop), so the caller can show the path instead."""
    if not folder.is_dir():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except OSError:
        return False
    return True


def _windows_documents_dir() -> Path | None:
    """Documents as Windows knows it (FOLDERID_Documents), wherever it was moved."""
    try:
        import ctypes
        from ctypes import wintypes
        from uuid import UUID

        class _Guid(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8),
            ]

        folder_id = UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")
        guid = _Guid.from_buffer_copy(folder_id.bytes_le)
        path_pointer = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path_pointer)) != 0:
            return None
        try:
            folder = Path(path_pointer.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(path_pointer)
        return folder if folder.is_dir() else None
    except (AttributeError, OSError, ValueError):
        return None
