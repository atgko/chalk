"""Integration tests for chalk.cli (`python toolkit.py ...`), driving the
full init -> add -> extract -> rollover -> export -> status loop against
a real project directory, with no UI and no network."""

import io
import os

import pytest

from chalk import metrics
from chalk.cli import main
from chalk.project import ProjectPaths, load_course
from tests.fixtures import docx_builder, md_builder


class _Run:
    def __init__(self, code: int, out: str, err: str):
        self.code, self.out, self.err = code, out, err


def run(*argv, answers=()):
    pending = list(answers)
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), input_fn=lambda _prompt: pending.pop(0), out=out, err=err)
    assert not pending, "not every scripted answer was consumed"
    return _Run(code, out.getvalue(), err.getvalue())


@pytest.fixture
def project(tmp_path):
    result = run("init", "--name", "IS-6640", "--dir", str(tmp_path))
    assert result.code == 0
    return tmp_path / "IS-6640"


def _extract(project, syllabus, *extra, answers=()):
    return run("extract", str(syllabus), "--project", str(project), *extra, answers=answers)


# ---- init / add / status --------------------------------------------------------


def test_init_creates_a_project_and_explains_next_steps(project):
    assert (project / "config.json").exists()


def test_init_into_a_non_empty_folder_prints_a_plain_error(tmp_path):
    (tmp_path / "Course").mkdir()
    (tmp_path / "Course" / "x.txt").write_text("x", encoding="utf-8")

    result = run("init", "--name", "Course", "--dir", str(tmp_path))

    assert result.code == 1
    assert result.err.startswith("Error: A folder named 'Course' already exists")
    assert "Traceback" not in result.err


def test_commands_outside_a_project_explain_what_is_wrong(tmp_path):
    result = run("status", "--project", str(tmp_path))
    assert result.code == 1
    assert "isn't a Chalk course project" in result.err


def test_add_indexes_a_source_file(project, tmp_path):
    material = tmp_path / "ch3.txt"
    material.write_text("notes", encoding="utf-8")

    result = run("add", str(material), "--project", str(project))

    assert result.code == 0
    assert "Added ch3.txt" in result.out
    assert (project / "source" / "ch3.txt").exists()


def test_status_of_a_fresh_project(project):
    result = run("status", "--project", str(project))
    assert result.code == 0
    assert "No course.json yet" in result.out
    assert "Outputs:       none yet" in result.out
    assert "$0.0000" in result.out


# ---- extract ---------------------------------------------------------------------


def test_extract_saves_course_json_and_brief(project, tmp_path):
    syllabus = docx_builder.build_minimal_syllabus(tmp_path / "syllabus.docx")

    result = _extract(project, syllabus)

    assert result.code == 0
    assert "Extracted: IS 6640 Networking and Servers — Fall 2026" in result.out
    assert "Wrote course.json" in result.out
    assert "Wrote outputs/course-brief.md" in result.out
    assert load_course(ProjectPaths(project)).course.term == "Fall 2026"


def test_extract_failure_prints_the_prd_message(project, tmp_path):
    syllabus = md_builder.build_syllabus_with_no_schedule_table(tmp_path / "s.md")
    result = _extract(project, syllabus)
    assert result.code == 1
    assert "No schedule table found" in result.err


def test_failed_consistency_check_can_be_cancelled(project, tmp_path):
    syllabus = docx_builder.build_syllabus_with_term_mismatch(tmp_path / "bad.docx")

    result = _extract(project, syllabus, answers=["n"])

    assert result.code == 1
    assert "Term and schedule don't match" in result.out
    assert "course.json was not saved" in result.out
    assert not (project / "course.json").exists()
    assert metrics.read_events_by_type(project / "eval-log.json", "consistency_check_override") == []


@pytest.mark.parametrize(("extra", "answers"), [((), ["y"]), (("--continue-anyway",), [])])
def test_overriding_the_consistency_check_saves_and_logs_the_override(project, tmp_path, extra, answers):
    syllabus = docx_builder.build_syllabus_with_term_mismatch(tmp_path / "bad.docx")

    result = _extract(project, syllabus, *extra, answers=answers)

    assert result.code == 0
    assert (project / "course.json").exists()
    overrides = metrics.read_events_by_type(project / "eval-log.json", "consistency_check_override")
    assert overrides[-1]["term"] == "Spring 2026"


# ---- rollover --------------------------------------------------------------------


def test_rollover_before_extraction_redirects_to_extract(project):
    result = run("rollover", "--term", "Fall 2027", "--project", str(project), "--yes")
    assert result.code == 1
    assert "Upload and extract a syllabus first" in result.err


def test_rollover_prints_the_preview_then_writes_on_confirm(project, tmp_path):
    _extract(project, docx_builder.build_minimal_syllabus(tmp_path / "s.docx"))

    result = run("rollover", "--term", "Fall 2027", "--no-llm", "--project", str(project), answers=["y"])

    assert result.code == 0
    assert "ROLLOVER PREVIEW: IS 6640 (2 weeks) → Fall 2027" in result.out
    assert 'Term label:   "Fall 2026"     → "Fall 2027"' in result.out
    assert "Week 1:       Aug 24 (8/24)   → Aug 23 (8/23)" in result.out
    assert "Week 2:       Oct 19 (10/19)  → Aug 30 (8/30)" in result.out
    assert "Fall Break (10/9 - 10/17)" in result.out
    assert "  outputs/syllabus.docx" in result.out
    assert "Wrote outputs/canvas.html" in result.out
    assert (project / "outputs" / "syllabus.docx").exists()


def test_rollover_shows_week_flags(project, tmp_path):
    # Minimal fixture's Week 2 is 10/19; Fall 2027 Week 2 lands on 8/30, but a
    # 9-week course's Week 8 (10/11) falls inside Fall Break 2027 (Oct 9-17).
    _extract(project, docx_builder.build_minimal_syllabus(tmp_path / "s.docx"))

    result = run("rollover", "--term", "Fall 2027", "--weeks", "9", "--no-llm", "--project", str(project), "--yes")

    assert "⚠ Fall Break 2027 is Oct 9–17 — confirm Week 8 timing" in result.out
    assert "(new week)" in result.out
    assert "Course length changed from 2 to 9 weeks" in result.out


def test_rollover_cancel_writes_nothing(project, tmp_path):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))

    result = run("rollover", "--term", "Fall 2027", "--no-llm", "--project", str(project), answers=["n"])

    assert result.code == 1
    assert "nothing was written" in result.out
    assert not (project / "outputs" / "syllabus.md").exists()


def test_rollover_asks_for_week1_date_when_term_is_not_in_calendar(project, tmp_path):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))

    result = run(
        "rollover", "--term", "Fall 2099", "--no-llm", "--project", str(project),
        answers=["2099-08-24", "y"],
    )

    assert result.code == 0
    assert "That term isn't in the calendar data yet" in result.out
    assert "Aug 24 (8/24)" in result.out


def test_rollover_rejects_a_malformed_typed_week1_date(project, tmp_path):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))

    result = run("rollover", "--term", "Fall 2099", "--project", str(project), answers=["next monday"])

    assert result.code == 1
    assert "isn't a date in YYYY-MM-DD form" in result.err


def test_rollover_with_yes_and_unknown_term_fails_instead_of_prompting(project, tmp_path):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    result = run("rollover", "--term", "Fall 2099", "--project", str(project), "--yes")
    assert result.code == 1
    assert "That term isn't in the calendar data yet" in result.err


def test_rollover_accepts_week1_date_flag(project, tmp_path):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    result = run(
        "rollover", "--term", "Fall 2099", "--week1-date", "2099-08-24", "--no-llm",
        "--project", str(project), "--yes",
    )
    assert result.code == 0


def test_week1_date_flag_rejects_bad_dates(project):
    with pytest.raises(SystemExit):
        run("rollover", "--term", "Fall 2099", "--week1-date", "8/24", "--project", str(project))


def test_rollover_loads_the_project_env_without_overriding_the_shell(project, tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "from-shell")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    (project / ".env").write_text("LLM_PROVIDER=anthropic\nLLM_MODEL=from-env-file\n", encoding="utf-8")
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))

    run("rollover", "--term", "Fall 2027", "--no-llm", "--project", str(project), "--yes")

    assert os.environ["LLM_PROVIDER"] == "anthropic"
    assert os.environ["LLM_MODEL"] == "from-shell"
    monkeypatch.delenv("LLM_PROVIDER")  # load_dotenv set it outside monkeypatch's tracking


# ---- export / generate / full status -----------------------------------------------


def test_export_writes_canvas_and_brief(project, tmp_path):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    result = run("export", "--project", str(project))
    assert result.code == 0
    assert "Wrote outputs/canvas.html" in result.out
    assert (project / "outputs" / "canvas.html").exists()


@pytest.fixture
def llm(monkeypatch, project):
    """A configured provider (via the project's .env) and a mocked LLM."""
    for key in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    (project / ".env").write_text("LLM_PROVIDER=openai\nLLM_API_KEY=sk\nLLM_MODEL=gpt-4o\n", encoding="utf-8")
    calls = []

    def _complete(prompt, system="", max_tokens=2000):
        calls.append(prompt)
        return {"text": f"## Questions\nQ1. Draft {len(calls)}", "input_tokens": 1000, "output_tokens": 500}

    monkeypatch.setattr("chalk.generation.engine.complete", _complete)
    return calls


def test_generate_without_a_provider_explains_how_to_configure_one(project, tmp_path, monkeypatch):
    for key in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    result = run("generate", "quiz", "--week", "1", "--project", str(project))
    assert result.code == 1
    assert "No LLM provider is configured" in result.err


def test_generate_quiz_writes_a_bannered_draft_and_reports_cost(project, tmp_path, llm):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))

    result = run("generate", "quiz", "--week", "2", "--count", "4", "--format", "short answer",
                 "--project", str(project))

    assert result.code == 0, result.err
    assert "Estimated cost: up to ~$" in result.out
    assert "Wrote outputs/quizzes/week-2-quiz.md" in result.out
    assert "Tokens: 1,000 in / 500 out · Cost: $0.0075" in result.out
    text = (project / "outputs" / "quizzes" / "week-2-quiz.md").read_text(encoding="utf-8")
    assert text.startswith("> **AI-generated draft**")
    assert "Generate 4 questions in short answer format." in llm[0]


def test_generate_asks_before_overwriting_and_can_be_cancelled(project, tmp_path, llm):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    run("generate", "summary", "--week", "1", "--project", str(project))

    result = run("generate", "summary", "--week", "1", "--project", str(project), answers=["n"])

    assert result.code == 1
    assert "Cancelled — nothing was generated." in result.out
    assert len(llm) == 1


def test_generate_overwrite_with_yes_archives_the_old_draft(project, tmp_path, llm):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    run("generate", "discussion", "--week", "1", "--project", str(project))

    result = run("generate", "discussion", "--week", "1", "--yes", "--project", str(project))

    assert result.code == 0
    assert len(list((project / "outputs" / "discussions" / ".archive").iterdir())) == 1


def test_generate_per_week_types_need_a_week(project, tmp_path, llm):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    result = run("generate", "quiz", "--project", str(project))
    assert result.code == 1
    assert "Say which week" in result.err


def test_generate_rubric_from_a_description_file(project, tmp_path, llm):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    description = tmp_path / "lab3.md"
    description.write_text("Configure two VLANs and a trunk.", encoding="utf-8")

    result = run("generate", "rubric", "--assignment", "Lab 3", "--description-file", str(description),
                 "--points", "40", "--project", str(project))

    assert result.code == 0, result.err
    assert "Wrote outputs/rubrics/lab-3-rubric.md" in result.out
    assert "Configure two VLANs and a trunk." in llm[0]
    assert "worth 40 points" in llm[0]


def test_generate_rubric_with_a_missing_description_file(project, tmp_path, llm):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    result = run("generate", "rubric", "--assignment", "Lab", "--description-file", str(tmp_path / "nope.md"),
                 "--project", str(project))
    assert "Couldn't find" in result.err


def test_generate_grounds_in_selected_sources_and_reports_unknown_cost(project, tmp_path, llm, monkeypatch):
    _extract(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    material = tmp_path / "ch1.txt"
    material.write_text("Intro chapter summary", encoding="utf-8")
    run("add", str(material), "--project", str(project))
    monkeypatch.setenv("LLM_MODEL", "gpt-unlisted")

    result = run("generate", "slides", "--week", "1", "--notes", "OSI layers", "--source", "ch1.txt",
                 "--project", str(project))

    assert result.code == 0, result.err
    assert "Intro chapter summary" in llm[0] and "OSI layers" in llm[0]
    assert "Cost: unknown (no cost rate for this model in config.json)" in result.out


def test_status_after_a_full_loop(project, tmp_path):
    material = tmp_path / "ch3.txt"
    material.write_text("notes", encoding="utf-8")
    _extract(project, docx_builder.build_minimal_syllabus(tmp_path / "s.docx"))
    run("add", str(material), "--project", str(project))
    run("rollover", "--term", "Fall 2027", "--no-llm", "--project", str(project), "--yes")

    result = run("status", "--project", str(project))

    assert "Course:        IS 6640 Networking and Servers — Fall 2027, 2 weeks" in result.out
    assert "Source files:  2 (ch3.txt, s.docx)" in result.out
    assert "top-level: 3" in result.out
    assert "Rollovers:     1" in result.out
