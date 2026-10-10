"""Tests for chalk.generation.library: finding saved drafts for the
Drafts tab, in content-type then week order, with their archived
versions counted."""

import datetime as dt
import os

from chalk.generation.library import list_saved_drafts


def _write(path, text="draft"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_empty_project_has_no_saved_drafts(tmp_project):
    assert list_saved_drafts(tmp_project) == []


def test_drafts_are_listed_by_type_then_week(tmp_project):
    out = tmp_project.outputs_dir
    _write(out / "discussions" / "week-2-discussion.md")
    _write(out / "quizzes" / "week-10-quiz.md")
    _write(out / "quizzes" / "week-3-quiz.md")
    _write(out / "rubrics" / "lab-3-rubric.md")

    drafts = list_saved_drafts(tmp_project)

    assert [(d.spec.key, d.week_number, d.path.name) for d in drafts] == [
        ("quiz", 3, "week-3-quiz.md"),
        ("quiz", 10, "week-10-quiz.md"),
        ("discussion", 2, "week-2-discussion.md"),
        ("rubric", None, "lab-3-rubric.md"),
    ]


def test_titles_name_the_week_or_the_assignment(tmp_project):
    out = tmp_project.outputs_dir
    _write(out / "summaries" / "week-4-summary.md")
    _write(out / "assignments" / "network-design-assignment.md")

    titles = {d.path.name: d.title for d in list_saved_drafts(tmp_project)}

    assert titles == {
        "week-4-summary.md": "Week 4 — Module summary",
        "network-design-assignment.md": "Network design — Assignment creator / enhancer",
    }


def test_archived_versions_are_counted_not_listed(tmp_project):
    quizzes = tmp_project.outputs_dir / "quizzes"
    _write(quizzes / "week-3-quiz.md")
    _write(quizzes / ".archive" / "week-3-quiz-20261001-101500.md")
    _write(quizzes / ".archive" / "week-3-quiz-20261002-090000.md")
    _write(quizzes / ".archive" / "week-13-quiz-20261002-090000.md")

    (draft,) = list_saved_drafts(tmp_project)

    assert draft.path.name == "week-3-quiz.md"
    assert draft.archived_versions == 2


def test_other_files_in_output_folders_are_ignored(tmp_project):
    out = tmp_project.outputs_dir
    _write(out / "quizzes" / "notes.txt")
    _write(out / "quizzes" / "my-own-quiz.md")
    _write(out / "canvas.html")

    assert list_saved_drafts(tmp_project) == []


def test_saved_at_is_the_file_time(tmp_project):
    path = _write(tmp_project.outputs_dir / "slides" / "week-1-slides.md")
    saved = dt.datetime(2026, 10, 9, 20, 30, tzinfo=dt.UTC)
    os.utime(path, (saved.timestamp(), saved.timestamp()))

    (draft,) = list_saved_drafts(tmp_project)

    assert draft.saved_at == saved
    assert draft.saved_at.tzinfo is not None  # local time, for display
