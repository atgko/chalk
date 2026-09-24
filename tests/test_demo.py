"""Tests for the demo course: it builds, the sample files exercise the
features they're meant to show, reopening is idempotent, and reset is
safe."""

import pytest

from chalk.demo import DEMO_MARKER, TRY_THESE_DIR, demo_project_name, open_demo_project
from chalk.errors import ProjectError
from chalk.pipeline import extract_syllabus, preview_rollover
from chalk.project import ProjectPaths, list_source_files, load_course


@pytest.fixture
def demo(tmp_path):
    return open_demo_project(tmp_path)


def _all_flags(plan):
    return [*plan.preview.general_flags, *(f for c in plan.preview.week_changes for f in c.flags)]


def test_demo_project_is_ready_to_use(demo):
    course = load_course(demo)
    assert demo.root.name == "Chalk-Demo"
    assert course.course.number == "IS 6640"
    assert course.course.duration_weeks == 10
    assert len(course.learning_objectives) == 4
    assert sum(a.weight for a in course.assessments) == pytest.approx(1.0)
    assert [w.label for w in course.weeks if w.is_break] == ["Fall Break (10/10 - 10/18)"]
    assert course.weeks[0].notes == "Video Quizzes are Taken After Reading Each Chapter"
    assert demo.course_brief.exists()
    assert "week-3-subnetting-notes.md" in list_source_files(demo)
    assert (demo.root / DEMO_MARKER).exists()


def test_demo_rollover_reproduces_the_prd_worked_example(demo):
    plan = preview_rollover(demo, load_course(demo), "Fall 2027", llm_generate_topics=False)
    week1 = next(c for c in plan.preview.week_changes if c.week_number == 1)
    assert week1.new_date.isoformat() == "2027-08-23"
    assert "Fall Break 2027 is Oct 9–17 — confirm Week 8 timing" in _all_flags(plan)
    assert "Labor Day 2027 is Sep 6 — confirm Week 3 timing" in _all_flags(plan)  # DEMO.md step 3


def test_term_bug_sample_trips_the_consistency_check(demo):
    _, consistency = extract_syllabus(demo, demo.root / TRY_THESE_DIR / "IS-6640-Spring-2026-term-label-bug.docx")
    assert not consistency.passed
    assert "Spring 2026" in consistency.detail


def test_markdown_sample_extracts_and_shows_the_dst_flag_at_rollover(demo):
    course, consistency = extract_syllabus(demo, demo.root / TRY_THESE_DIR / "IS-4490-Fall-2026.md")
    assert consistency.passed
    assert course.course.duration_weeks == 15
    assert [w.label for w in course.weeks if w.is_break] == ["Fall Break", "Thanksgiving Break"]

    plan = preview_rollover(demo, course, "Fall 2027", llm_generate_topics=False)
    assert any("DST boundary" in flag for flag in _all_flags(plan))


def test_reopening_returns_the_existing_demo_unchanged(demo, tmp_path):
    (demo.outputs_dir / "marker.txt").write_text("keep", encoding="utf-8")
    again = open_demo_project(tmp_path)
    assert again == demo
    assert (demo.outputs_dir / "marker.txt").exists()


def test_reset_rebuilds_but_keeps_the_saved_provider_settings(demo, tmp_path):
    demo.env.write_text("LLM_PROVIDER=openai\nLLM_API_KEY=sk-keep\nLLM_MODEL=gpt-4o\n", encoding="utf-8")
    (demo.outputs_dir / "scratch.txt").write_text("x", encoding="utf-8")

    reset = open_demo_project(tmp_path, reset=True)

    assert not (reset.outputs_dir / "scratch.txt").exists()
    assert "sk-keep" in reset.env.read_text(encoding="utf-8")
    assert load_course(reset).course.term == "Fall 2026"


def test_reset_without_a_saved_env(demo, tmp_path):
    assert not open_demo_project(tmp_path, reset=True).env.exists()


def test_never_touches_a_same_named_folder_that_is_not_the_demo(tmp_path):
    real = tmp_path / demo_project_name()
    real.mkdir()
    (real / "my-course.docx").write_bytes(b"important")

    with pytest.raises(ProjectError, match="isn't the demo course"):
        open_demo_project(tmp_path, reset=True)
    assert (real / "my-course.docx").read_bytes() == b"important"


def test_an_empty_same_named_folder_becomes_the_demo(tmp_path):
    (tmp_path / demo_project_name()).mkdir()
    assert load_course(ProjectPaths(open_demo_project(tmp_path).root)) is not None
