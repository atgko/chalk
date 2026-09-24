"""The demo course: a ready-to-use project for showing Chalk to someone.

`open_demo_project()` creates (or reopens) a project with the sample
IS 6640 syllabus already extracted and saved, one source-material file
indexed, and a `try-these/` folder of files to upload live:

- the same syllabus mislabeled "Spring 2026", to show the consistency
  check catching the sponsor's real bug
- IS 4490 as a markdown syllabus, to show the markdown path and the
  daylight-saving flag at rollover

Reset deletes and rebuilds the demo folder, but only a folder carrying
the demo marker file, so it can never delete a real course project. The
instructor's saved AI provider settings (.env) survive a reset.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from chalk import branding
from chalk.demo_content import (
    build_is4490_markdown_syllabus,
    build_is6640_term_mismatch_syllabus,
    build_is6640_word_syllabus,
    write_subnetting_notes,
)
from chalk.errors import ProjectError
from chalk.pipeline import extract_syllabus, save_reviewed_course
from chalk.project import ProjectPaths, add_source, init_project, open_project

DEMO_MARKER = ".chalk-demo"
TRY_THESE_DIR = "try-these"


def demo_project_name() -> str:
    return f"{branding.PROJECT_NAME}-Demo"


def open_demo_project(parent_dir, *, reset: bool = False) -> ProjectPaths:
    root = Path(parent_dir) / demo_project_name()
    if root.exists() and any(root.iterdir()):
        if not (root / DEMO_MARKER).exists():
            raise ProjectError(
                f"'{root}' exists but isn't the demo course, so it was left alone. "
                "Move or rename it to use the demo."
            )
        if not reset:
            return open_project(root)
        saved_env = (root / ".env").read_bytes() if (root / ".env").exists() else None
        shutil.rmtree(root)
    else:
        saved_env = None

    paths = _build(Path(parent_dir))
    if saved_env is not None:
        paths.env.write_bytes(saved_env)
    return paths


def _build(parent_dir: Path) -> ProjectPaths:
    paths = init_project(parent_dir, demo_project_name())
    (paths.root / DEMO_MARKER).write_text(
        "This folder is the demo course. Resetting the demo deletes and rebuilds it.\n", encoding="utf-8"
    )

    try_these = paths.root / TRY_THESE_DIR
    try_these.mkdir()
    syllabus = build_is6640_word_syllabus(try_these / "IS-6640-Fall-2026.docx")
    build_is6640_term_mismatch_syllabus(try_these / "IS-6640-Spring-2026-term-label-bug.docx")
    build_is4490_markdown_syllabus(try_these / "IS-4490-Fall-2026.md")
    notes = write_subnetting_notes(try_these / "week-3-subnetting-notes.md")

    course_data, _ = extract_syllabus(paths, syllabus)
    save_reviewed_course(paths, course_data)
    add_source(paths, notes)
    return paths
