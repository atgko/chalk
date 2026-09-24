"""Tests for chalk.project (F-06): init, open, course.json I/O, add, status."""

import datetime as dt
import json

import pytest

from chalk import metrics
from chalk.errors import ProjectError
from chalk.project import (
    OUTPUT_SUBDIRS,
    ProjectPaths,
    add_source,
    init_project,
    list_source_files,
    load_course,
    open_project,
    project_status,
    require_course,
    save_course,
)
from tests.sample_course import build_sample_course_data

# ---- init ------------------------------------------------------------------------


def test_init_creates_the_prd_directory_layout(tmp_project):
    root = tmp_project.root
    for relative in ("source", "outputs", "prompts", "data"):
        assert (root / relative).is_dir()
    for subdir in OUTPUT_SUBDIRS:
        assert (root / "outputs" / subdir).is_dir()


def test_init_copies_bundled_config_and_calendars(tmp_project):
    config = json.loads(tmp_project.config_json.read_text(encoding="utf-8"))
    assert config["institution"] == "University of Utah"
    assert "local" in config["cost_rates"]
    calendars = json.loads(tmp_project.calendars_json.read_text(encoding="utf-8"))
    assert calendars["terms"]


def test_init_copies_prompt_templates_when_resources_have_them(tmp_path):
    resources = tmp_path / "resources"
    (resources / "data").mkdir(parents=True)
    (resources / "prompts").mkdir()
    (resources / "config.json").write_text("{}", encoding="utf-8")
    (resources / "data" / "calendars.json").write_text('{"terms": []}', encoding="utf-8")
    (resources / "prompts" / "quiz.txt").write_text("Quiz for {course_title}", encoding="utf-8")

    paths = init_project(tmp_path, "Course", resources_dir=resources)

    assert (paths.prompts_dir / "quiz.txt").read_text(encoding="utf-8") == "Quiz for {course_title}"


def test_init_gitignores_the_env_file_and_writes_a_readme(tmp_project):
    assert ".env" in (tmp_project.root / ".gitignore").read_text(encoding="utf-8")
    assert tmp_project.readme.read_text(encoding="utf-8").startswith("# IS-6640-Test")


def test_init_refuses_a_non_empty_existing_folder(tmp_path):
    (tmp_path / "Course").mkdir()
    (tmp_path / "Course" / "notes.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(ProjectError, match="already exists"):
        init_project(tmp_path, "Course")
    assert (tmp_path / "Course" / "notes.txt").read_text(encoding="utf-8") == "keep me"


def test_init_accepts_an_existing_empty_folder(tmp_path):
    (tmp_path / "Course").mkdir()
    assert init_project(tmp_path, "Course").config_json.exists()


@pytest.mark.parametrize("bad_name", ["", "   ", "a/b", "a\\b", "..", "."])
def test_init_rejects_unusable_names(tmp_path, bad_name):
    with pytest.raises(ProjectError, match="isn't a usable project name"):
        init_project(tmp_path, bad_name)


# ---- open ------------------------------------------------------------------------


def test_open_project_accepts_an_initialized_project(tmp_project):
    assert open_project(tmp_project.root) == tmp_project


def test_open_project_rejects_a_folder_without_config(tmp_path):
    with pytest.raises(ProjectError, match="isn't a Chalk course project"):
        open_project(tmp_path)


# ---- course.json ------------------------------------------------------------------


def test_load_course_returns_none_before_any_extraction(tmp_project):
    assert load_course(tmp_project) is None


def test_require_course_raises_a_plain_english_error_when_missing(tmp_project):
    with pytest.raises(ProjectError, match="Upload and extract a syllabus first"):
        require_course(tmp_project)


def test_save_then_load_round_trips(tmp_project):
    course_data = build_sample_course_data()
    save_course(tmp_project, course_data)
    assert load_course(tmp_project) == course_data
    assert require_course(tmp_project) == course_data


def test_resaving_course_json_archives_the_previous_version(tmp_project):
    course_data = build_sample_course_data()
    save_course(tmp_project, course_data)
    save_course(tmp_project, course_data)

    archived = list((tmp_project.root / ".archive").glob("course-*.json"))
    assert len(archived) == 1
    assert len(metrics.read_events_by_type(tmp_project.eval_log, "archive")) == 1


def test_syllabus_output_path_depends_on_source_format(tmp_project):
    assert tmp_project.syllabus_output("word").name == "syllabus.docx"
    assert tmp_project.syllabus_output("markdown").name == "syllabus.md"


# ---- add ------------------------------------------------------------------------


def test_add_copies_the_file_into_source_and_logs_an_event(tmp_project, tmp_path):
    material = tmp_path / "chapter-3-summary.txt"
    material.write_text("summary", encoding="utf-8")

    destination = add_source(tmp_project, material)

    assert destination == tmp_project.source_dir / "chapter-3-summary.txt"
    assert destination.read_text(encoding="utf-8") == "summary"
    events = metrics.read_events_by_type(tmp_project.eval_log, "source_indexed")
    assert events[-1]["filename"] == "chapter-3-summary.txt"
    assert events[-1]["source_count"] == 1


def test_add_updates_course_json_source_materials_when_a_course_exists(tmp_project, tmp_path):
    save_course(tmp_project, build_sample_course_data())
    material = tmp_path / "reading.pdf"
    material.write_bytes(b"%PDF-1.4")
    added_at = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.timezone.utc)

    add_source(tmp_project, material, now=added_at)
    add_source(tmp_project, material, now=added_at)  # re-adding doesn't duplicate

    refs = load_course(tmp_project).source_materials
    assert [(r.filename, r.added_at) for r in refs] == [("reading.pdf", added_at)]


def test_readding_a_file_archives_the_older_copy(tmp_project, tmp_path):
    material = tmp_path / "notes.md"
    material.write_text("v1", encoding="utf-8")
    add_source(tmp_project, material)
    material.write_text("v2", encoding="utf-8")
    add_source(tmp_project, material)

    assert (tmp_project.source_dir / "notes.md").read_text(encoding="utf-8") == "v2"
    assert len(list((tmp_project.source_dir / ".archive").iterdir())) == 1


def test_adding_a_file_already_in_source_leaves_it_in_place(tmp_project):
    in_place = tmp_project.source_dir / "notes.md"
    in_place.write_text("original", encoding="utf-8")

    assert add_source(tmp_project, in_place) == in_place
    assert in_place.read_text(encoding="utf-8") == "original"
    assert not (tmp_project.source_dir / ".archive").exists()


def test_add_rejects_unsupported_file_types(tmp_project, tmp_path):
    image = tmp_path / "diagram.png"
    image.write_bytes(b"png")
    with pytest.raises(ProjectError, match=r"\.pdf, \.docx, \.md, \.txt"):
        add_source(tmp_project, image)


def test_add_reports_a_missing_file(tmp_project, tmp_path):
    with pytest.raises(ProjectError, match="Couldn't find"):
        add_source(tmp_project, tmp_path / "missing.pdf")


def test_list_source_files_is_empty_without_a_source_dir(tmp_path):
    assert list_source_files(ProjectPaths(tmp_path)) == []


# ---- status ----------------------------------------------------------------------


def test_status_of_a_fresh_project(tmp_project):
    status = project_status(tmp_project)
    assert status.name == "IS-6640-Test"
    assert status.course is None
    assert status.source_files == []
    assert set(status.output_counts.values()) == {0}
    assert status.total_cost_usd == 0


def test_status_summarizes_events_and_outputs(tmp_project):
    save_course(tmp_project, build_sample_course_data())
    (tmp_project.outputs_dir / "canvas.html").write_text("x", encoding="utf-8")
    (tmp_project.outputs_dir / "quizzes" / "week-3-quiz.md").write_text("x", encoding="utf-8")
    log = tmp_project.eval_log
    metrics.append_event(log, "generation", {"cost_usd": 0.012})
    metrics.append_event(log, "generation", {"cost_usd": 0.003})
    metrics.append_event(log, "rollover", {})
    metrics.append_event(log, "extraction_error", {})
    metrics.append_event(log, "consistency_check", {"passed": False})
    metrics.append_event(log, "consistency_check", {"passed": True})

    status = project_status(tmp_project)

    assert status.course.course.number == "IS 6640"
    assert status.output_counts["top-level"] == 1
    assert status.output_counts["quizzes"] == 1
    assert status.total_cost_usd == pytest.approx(0.015)
    assert status.rollover_count == 1
    assert status.extraction_error_count == 1
    assert status.consistency_failures == 1


def test_status_tolerates_a_missing_outputs_dir(tmp_path):
    paths = ProjectPaths(tmp_path)
    assert project_status(paths).output_counts["top-level"] == 0


# ---- export helpers ---------------------------------------------------------------

import io  # noqa: E402
import zipfile  # noqa: E402

from chalk.project import list_output_files, zip_outputs  # noqa: E402


def test_list_output_files_skips_archived_versions(tmp_project):
    (tmp_project.outputs_dir / "canvas.html").write_text("x", encoding="utf-8")
    (tmp_project.outputs_dir / "quizzes" / "week-1-quiz.md").write_text("q", encoding="utf-8")
    (tmp_project.outputs_dir / ".archive").mkdir()
    (tmp_project.outputs_dir / ".archive" / "canvas-1.html").write_text("old", encoding="utf-8")

    names = [p.relative_to(tmp_project.outputs_dir).as_posix() for p in list_output_files(tmp_project)]

    assert names == ["canvas.html", "quizzes/week-1-quiz.md"]


def test_list_output_files_without_an_outputs_dir(tmp_path):
    assert list_output_files(ProjectPaths(tmp_path)) == []


def test_zip_outputs_contains_every_current_output(tmp_project):
    (tmp_project.outputs_dir / "canvas.html").write_text("<table>", encoding="utf-8")
    (tmp_project.outputs_dir / "quizzes" / "week-1-quiz.md").write_text("q", encoding="utf-8")

    with zipfile.ZipFile(io.BytesIO(zip_outputs(tmp_project))) as archive:
        assert sorted(archive.namelist()) == ["canvas.html", "quizzes/week-1-quiz.md"]
        assert archive.read("canvas.html") == b"<table>"
