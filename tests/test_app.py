"""Streamlit smoke/flow tests (PLAN.md task 51) via streamlit.testing.v1.AppTest.

AppTest runs app.py in-process, so these drive the real views against a
real project directory. File uploads aren't driven through AppTest —
the upload logic (ui.upload_view.extract_upload) is tested directly in
test_ui_helpers.py, and upload results are injected via session state.
"""

import datetime as dt
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from chalk import metrics
from chalk.pipeline import extract_syllabus, save_reviewed_course
from chalk.project import ProjectPaths, load_course, save_course
from tests.fixtures import docx_builder, md_builder
from ui import session
from ui.common import NEEDS_COURSE_MESSAGE
from ui.session import PendingExtraction, TableChoice

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")
_ENV_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """The app loads the project's .env into os.environ; register every
    provider variable with monkeypatch so each test's changes are undone."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def project(tmp_project):
    (tmp_project.env).write_text(
        "LLM_PROVIDER=openai\nLLM_API_KEY=sk-test\nLLM_BASE_URL=https://api.openai.com/v1\nLLM_MODEL=gpt-4o\n",
        encoding="utf-8",
    )
    return tmp_project


@pytest.fixture
def saved_project(project, tmp_path):
    syllabus = md_builder.build_minimal_syllabus(tmp_path / "syllabus.md")
    course_data, _ = extract_syllabus(project, syllabus)
    save_reviewed_course(project, course_data)
    return project


def launch(paths=None, **state) -> AppTest:
    # Generous: each run is fast, but a busy machine (e.g. OneDrive syncing) can stall one.
    at = AppTest.from_file(APP_PATH, default_timeout=180)
    if paths is not None:
        at.session_state[session.PROJECT_ROOT_KEY] = str(paths.root)
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def widget(elements, label: str):
    """The last widget with this label (later tabs render later)."""
    matches = [e for e in elements if e.label == label]
    assert matches, f"no widget labeled {label!r}; have {[e.label for e in elements]}"
    return matches[-1]


def click(at: AppTest, label: str) -> AppTest:
    matches = [b for b in at.button if b.label == label]
    assert matches, f"no button labeled {label!r}; have {[b.label for b in at.button]}"
    return matches[0].click().run()


def texts(elements) -> list[str]:
    return [e.value for e in elements]


def assert_no_exception(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]


# ---- Launch / project picker ------------------------------------------------------


def test_launch_without_a_project_shows_the_picker():
    at = launch()
    assert_no_exception(at)
    assert at.title[0].value == "Chalk"
    assert {"Open project", "Create project"} <= {b.label for b in at.button}


def test_create_project_from_the_picker_then_see_first_run_setup(tmp_path):
    at = launch()
    inputs = {t.label: t for t in at.text_input}
    inputs["Create it inside"].input(str(tmp_path))
    inputs["Project name"].input("IS-6640-Fall-2027")
    at = click(at.run(), "Create project")

    assert_no_exception(at)
    assert (tmp_path / "IS-6640-Fall-2027" / "config.json").exists()
    assert at.title[0].value == "Welcome to Chalk"


def test_create_project_reads_the_name_on_click_and_confirms(tmp_path):
    at = launch()
    inputs = {t.label: t for t in at.text_input}
    inputs["Create it inside"].input(str(tmp_path))
    inputs["Project name"].input("IS-6640-Fall-2027")

    at = click(at, "Create project")  # no rerun between typing and clicking

    assert_no_exception(at)
    assert (tmp_path / "IS-6640-Fall-2027" / "config.json").exists()
    assert any("Created project IS-6640-Fall-2027" in s.value for s in at.success)


def test_create_project_without_a_name_asks_for_one(tmp_path):
    at = launch()
    {t.label: t for t in at.text_input}["Create it inside"].input(str(tmp_path))

    at = click(at, "Create project")

    assert any("Enter a project name" in w.value for w in at.warning)
    assert list(tmp_path.iterdir()) == []


def test_open_project_without_a_folder_asks_for_one():
    at = click(launch(), "Open project")

    assert any("Enter the project folder" in w.value for w in at.warning)
    assert "Open project" in {b.label for b in at.button}


def test_opening_a_project_confirms_which_one_opened(tmp_project):
    at = launch()
    {t.label: t for t in at.text_input}["Project folder"].input(str(tmp_project.root))

    at = click(at, "Open project")

    assert_no_exception(at)
    assert any(f"Opened project {tmp_project.root.name}" in s.value for s in at.success)


def test_opening_a_folder_that_is_not_a_project_shows_a_plain_error(tmp_path):
    at = launch()
    {t.label: t for t in at.text_input}["Project folder"].input(str(tmp_path))
    at = click(at.run(), "Open project")
    assert "isn't a Chalk course project" in at.error[0].value


def test_a_session_project_that_disappeared_falls_back_to_the_picker(tmp_path):
    at = launch(ProjectPaths(tmp_path / "gone"))
    assert "isn't a Chalk course project" in at.error[0].value
    assert "Open project" in {b.label for b in at.button}


# ---- First-run setup / Settings ------------------------------------------------------


def test_first_run_setup_can_be_skipped(tmp_project):
    at = launch(tmp_project)
    assert at.title[0].value == "Welcome to Chalk"

    at = click(at, "Skip for now")

    assert_no_exception(at)
    assert [t.label for t in at.tabs] == [
        "Upload",
        "Review",
        "Rollover",
        "Generate",
        "Export",
        "Metrics",
        "Settings",
    ]
    assert "Provider: Not configured" in at.caption[-1].value


def test_first_run_setup_validates_then_writes_env(tmp_project, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "chalk.config.complete", lambda prompt, max_tokens=5: calls.append(prompt) or {}
    )
    at = launch(tmp_project)
    at.radio[0].set_value("Local model (Ollama)")
    at = click(at.run(), "Test connection and continue")

    assert_no_exception(at)
    assert calls
    assert "LLM_BASE_URL=" in tmp_project.env.read_text(encoding="utf-8")
    assert "Provider: Local model llama3.1:70b" in at.caption[-1].value


def test_first_run_setup_shows_the_provider_error_and_writes_nothing(tmp_project, monkeypatch):
    from chalk.errors import LLMProviderError

    def _reject(prompt, max_tokens=5):
        raise LLMProviderError(
            "The OpenAI API key was not accepted. Check it at platform.openai.com and try again."
        )

    monkeypatch.setattr("chalk.config.complete", _reject)
    at = launch(tmp_project)
    at.text_input[0].input("sk-bad")
    at = click(at.run(), "Test connection and continue")

    assert "The OpenAI API key was not accepted" in at.error[0].value
    assert not tmp_project.env.exists()


def test_first_run_setup_requires_a_key_for_hosted_providers(tmp_project):
    at = click(launch(tmp_project), "Test connection and continue")
    assert "Paste your OpenAI API key" in at.error[0].value


def test_settings_keeps_the_saved_key_when_left_blank_and_switches_model(project, monkeypatch):
    monkeypatch.setattr("chalk.config.complete", lambda prompt, max_tokens=5: {})
    at = launch(project)
    widget(at.selectbox, "Model").set_value("gpt-4o-mini")
    at = click(at.run(), "Test connection and save")

    assert_no_exception(at)
    env_text = project.env.read_text(encoding="utf-8")
    assert "LLM_API_KEY='sk-test'" in env_text or "LLM_API_KEY=sk-test" in env_text
    assert "gpt-4o-mini" in env_text
    assert "Connected and saved." in texts(at.success)


# ---- Tab gating --------------------------------------------------------------------


def test_gated_tabs_redirect_until_a_course_exists(project):
    at = launch(project)
    assert_no_exception(at)
    assert texts(at.info).count(NEEDS_COURSE_MESSAGE) == 4


def test_unreadable_course_json_is_reported_not_raised(project):
    project.course_json.write_text("{not json", encoding="utf-8")
    at = launch(project)
    assert_no_exception(at)
    assert "course.json couldn't be read" in at.error[0].value


def test_unexpected_errors_in_a_tab_are_contained(saved_project, monkeypatch):
    def _boom(*args):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("ui.metrics_view.render", _boom)
    at = launch(saved_project)

    assert_no_exception(at)
    assert any("Something unexpected went wrong (RuntimeError)" in e.value for e in at.error)
    assert "Rollover" in [t.label for t in at.tabs]


# ---- Upload / Review ------------------------------------------------------------------


def _pending(project, tmp_path, builder, name, *, acknowledged=None):
    syllabus = builder(tmp_path / name)
    course_data, consistency = extract_syllabus(project, syllabus)
    ack = consistency.passed if acknowledged is None else acknowledged
    return PendingExtraction(course_data, consistency, ack)


def test_failed_consistency_check_blocks_review_until_continue_anyway(project, tmp_path):
    pending = _pending(
        project, tmp_path, docx_builder.build_syllabus_with_term_mismatch, "bad.docx"
    )
    at = launch(project, chalk_pending_extraction=pending)

    assert "Term and schedule don't match" in at.warning[0].value
    assert "Resolve the term/schedule warning on the Upload tab first." in texts(at.info)

    at = click(at, "Continue anyway")

    assert_no_exception(at)
    assert metrics.read_events_by_type(project.eval_log, "consistency_check_override")
    assert "Confirm and save" in {b.label for b in at.button}


def test_cancelling_a_failed_consistency_check_discards_the_extraction(project, tmp_path):
    pending = _pending(
        project, tmp_path, docx_builder.build_syllabus_with_term_mismatch, "bad.docx"
    )
    at = click(launch(project, chalk_pending_extraction=pending), "Cancel")
    assert at.session_state["chalk_pending_extraction"] is None


def test_table_picker_resolves_an_ambiguous_upload(project, tmp_path):
    upload = md_builder.build_syllabus_with_multiple_candidate_tables(tmp_path / "two.md")
    choice = TableChoice(upload, ["Week | Dates / 1 | first", "Week | Dates / 1 | Duplicate"])
    at = launch(project, chalk_table_choice=choice)
    assert "Multiple possible schedule tables" in at.warning[0].value

    at.radio[0].set_value(1)
    at = click(at.run(), "Use this table")

    assert_no_exception(at)
    pending = at.session_state["chalk_pending_extraction"]
    assert pending.course_data.weeks[0].topics == ["Duplicate table for ambiguity test"]
    assert at.session_state["chalk_table_choice"] is None



def test_continue_anyway_opens_the_review_tab(project, tmp_path):
    pending = _pending(
        project, tmp_path, docx_builder.build_syllabus_with_term_mismatch, "bad.docx"
    )
    at = launch(project, chalk_pending_extraction=pending)
    assert at.session_state[session.ACTIVE_TAB_KEY] == "Upload"

    at = click(at, "Continue anyway")

    assert at.session_state[session.ACTIVE_TAB_KEY] == "Review"


def test_extraction_opens_the_review_tab(project, tmp_path):
    upload = md_builder.build_syllabus_with_multiple_candidate_tables(tmp_path / "two.md")
    choice = TableChoice(upload, ["Week | Dates / 1 | first", "Week | Dates / 1 | Duplicate"])

    at = click(launch(project, chalk_table_choice=choice), "Use this table")

    assert_no_exception(at)
    assert at.session_state[session.ACTIVE_TAB_KEY] == "Review"


def test_failed_extraction_stays_on_the_upload_tab(project, tmp_path):
    upload = md_builder.build_syllabus_with_no_schedule_table(tmp_path / "bad.md")
    choice = TableChoice(upload, ["a", "b"])

    at = click(launch(project, chalk_table_choice=choice), "Use this table")

    assert at.error
    assert at.session_state[session.ACTIVE_TAB_KEY] == "Upload"

def test_table_picker_can_be_cancelled(project, tmp_path):
    choice = TableChoice(tmp_path / "x.md", ["a", "b"])
    at = click(launch(project, chalk_table_choice=choice), "Cancel")
    assert at.session_state["chalk_table_choice"] is None


def test_review_then_confirm_and_save_writes_course_json_and_brief(project, tmp_path):
    pending = _pending(project, tmp_path, md_builder.build_minimal_syllabus, "s.md")
    at = launch(project, chalk_pending_extraction=pending)
    assert "Newly extracted — not saved yet." in texts(at.caption)
    assert "IS 4490 Emerging Technologies" in [s.value for s in at.subheader]

    at.number_input[0].set_value(4)
    at = at.run()
    assert any("rollover will add 2 week(s)" in i for i in texts(at.info))
    at = click(at, "Confirm and save")

    assert_no_exception(at)
    assert load_course(project).course.duration_weeks == 4
    assert project.course_brief.exists()
    assert "Saved course.json and regenerated the course brief." in texts(at.success)


def test_discard_drops_the_unsaved_extraction_and_keeps_the_saved_course(saved_project, tmp_path):
    saved_title = load_course(saved_project).course.title
    pending = _pending(saved_project, tmp_path, docx_builder.build_minimal_syllabus, "new.docx")
    at = launch(saved_project, chalk_pending_extraction=pending)
    assert "Newly extracted — not saved yet." in texts(at.caption)

    at = click(at, "Discard")

    assert_no_exception(at)
    assert at.session_state[session._PENDING_EXTRACTION_KEY] is None
    assert "Discarded the new extraction. The saved course is unchanged." in texts(at.success)
    assert "Showing the saved course.json." in texts(at.caption)
    assert load_course(saved_project).course.title == saved_title


def test_discard_is_only_offered_for_an_unsaved_extraction(saved_project):
    assert "Discard" not in [b.label for b in launch(saved_project).button]


def _save_course_missing_details(project, tmp_path):
    course_data, _ = extract_syllabus(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    blank = course_data.course.model_copy(update={"section": "", "credits": None, "instructor": ""})
    save_course(project, course_data.model_copy(update={"course": blank}))


def test_review_lets_the_instructor_fill_in_missing_details(project, tmp_path):
    _save_course_missing_details(project, tmp_path)
    at = launch(project)
    assert "Blank fields weren't found in the syllabus — fill them in here." in texts(at.caption)

    widget(at.text_input, "Section").set_value("001")
    widget(at.text_input, "Credits").set_value("3")
    widget(at.text_input, "Instructor").set_value("Matt Pecsok")
    at = click(at.run(), "Confirm and save")

    assert_no_exception(at)
    course = load_course(project).course
    assert (course.section, course.credits, course.instructor) == ("001", 3, "Matt Pecsok")


def test_review_rejects_non_numeric_credits(project, tmp_path):
    _save_course_missing_details(project, tmp_path)
    at = launch(project)

    widget(at.text_input, "Credits").set_value("three")
    at = click(at.run(), "Confirm and save")

    assert any("Credits must be a whole number" in e for e in texts(at.error))
    assert load_course(project).course.credits is None


def test_review_shows_the_saved_course_when_nothing_is_pending(saved_project):
    at = launch(saved_project)
    assert "Showing the saved course.json." in texts(at.caption)
    assert "Upload a syllabus" not in texts(at.info)


def test_review_handles_a_course_without_objectives_or_assessments(project, tmp_path):
    course_data, _ = extract_syllabus(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    save_course(
        project,
        course_data.model_copy(
            update={"learning_objectives": [], "assessments": [], "university_dates": []}
        ),
    )
    at = launch(project)
    assert texts(at.caption).count("None found in the syllabus.") == 2


def test_review_warns_when_assessment_weights_do_not_add_up(project, tmp_path):
    from chalk.models import Assessment

    course_data, _ = extract_syllabus(project, md_builder.build_minimal_syllabus(tmp_path / "s.md"))
    save_course(project, course_data.model_copy(update={"assessments": [Assessment(name="Labs", weight=0.4)]}))
    at = launch(project)
    assert any("add up to 40%, not 100%" in w for w in texts(at.warning))


def test_other_tabs_warn_while_a_new_extraction_is_unsaved(saved_project, tmp_path):
    pending = _pending(saved_project, tmp_path, md_builder.build_minimal_syllabus, "new.md")
    at = launch(saved_project, chalk_pending_extraction=pending)

    warnings = [w for w in texts(at.warning) if "haven't saved it yet" in w]
    assert len(warnings) == 3  # Rollover, Generate, Export
    assert "Confirm and save" in warnings[0]


def test_no_unsaved_warning_once_nothing_is_pending(saved_project):
    assert not any("haven't saved it yet" in w for w in texts(launch(saved_project).warning))


def test_review_without_any_course_asks_for_an_upload(project):
    assert "Upload and extract a syllabus first." in texts(launch(project).info)


# ---- Rollover -------------------------------------------------------------------------


def test_rollover_preview_then_confirm_writes_files(saved_project):
    at = launch(saved_project)
    assert widget(at.selectbox, "Target term").value == "Fall 2027"

    at = click(at, "Preview rollover")
    assert_no_exception(at)
    assert any("Rollover preview: IS 4490 (2 weeks) → Fall 2027" in s.value for s in at.subheader)
    assert any("`outputs/syllabus.md`" in m.value for m in at.markdown)

    at = click(at, "Confirm rollover")

    assert_no_exception(at)
    assert "Rollover complete. Previous versions were archived." in texts(at.success)
    assert load_course(saved_project).course.term == "Fall 2027"
    assert saved_project.syllabus_output("markdown").exists()


def test_rollover_preview_can_be_cancelled(saved_project):
    at = click(click(launch(saved_project), "Preview rollover"), "Cancel")
    assert at.session_state["chalk_rollover_plan"] is None
    assert not saved_project.syllabus_output("markdown").exists()


def test_rollover_to_a_term_missing_from_the_calendar(saved_project):
    at = launch(saved_project)
    widget(at.selectbox, "Target term").set_value("Another term (not in the calendar)")
    at = at.run()
    assert any("That term isn't in the calendar data yet" in i for i in texts(at.info))
    widget(at.text_input, "Term name").input("Fall 2099")
    at.date_input[0].set_value(dt.date(2099, 8, 24))
    at = click(at.run(), "Preview rollover")

    assert_no_exception(at)
    assert any("→ Fall 2099" in s.value for s in at.subheader)


def test_lengthening_offers_ai_drafts_and_shows_the_flags(saved_project):
    at = launch(saved_project)
    widget(at.number_input, "Duration (weeks)").set_value(9)
    at = at.run()
    checkbox = at.checkbox[0]
    assert checkbox.value is True  # a provider is configured
    checkbox.uncheck()
    at = click(at.run(), "Preview rollover")

    assert_no_exception(at)
    warnings = texts(at.warning)
    assert any("Course length changed from 2 to 9 weeks" in w for w in warnings)
    assert any("confirm Week 8 timing" in w for w in warnings)


def test_meeting_days_and_break_toggles_narrow_the_flags(saved_project):
    at = launch(saved_project)
    widget(at.number_input, "Duration (weeks)").set_value(9)
    at = at.run()
    at.checkbox[0].uncheck()
    widget(at.multiselect, "Class meets on").set_value(["Tue", "Thu"])
    fall_break = next(t for t in at.toggle if t.label.startswith("Class takes Fall Break off"))
    assert fall_break.value is True
    fall_break.set_value(False)
    at = click(at.run(), "Preview rollover")

    assert_no_exception(at)
    warnings = texts(at.warning)
    assert not any("confirm Week 8 timing" in w for w in warnings)
    assert any("meets through Fall Break" in w for w in warnings)


def test_rollover_errors_are_shown_plainly(saved_project):
    (saved_project.source_dir / "syllabus.md").unlink()
    at = click(click(launch(saved_project), "Preview rollover"), "Confirm rollover")
    assert any("original syllabus" in e.value for e in at.error)


# ---- Generate / Export / Metrics ----------------------------------------------------------


@pytest.fixture
def llm(monkeypatch):
    calls = []

    def _complete(prompt, system="", max_tokens=2000):
        calls.append(prompt)
        return {
            "text": f"## Questions\nQ1. Draft number {len(calls)}",
            "input_tokens": 1000,
            "output_tokens": 500,
        }

    monkeypatch.setattr("chalk.generation.engine.complete", _complete)
    return calls


def test_generate_asks_for_a_provider_when_none_is_configured(saved_project):
    saved_project.env.unlink()
    at = launch(saved_project, chalk_setup_skipped=True)
    assert "Connect an AI provider in the Settings tab to generate content." in texts(at.info)


def test_generate_shows_the_estimate_and_no_materials_nudge(saved_project):
    at = launch(saved_project)
    assert any(c.startswith("Estimated cost: up to ~$") for c in texts(at.caption))
    assert "No source materials added yet" in " ".join(texts(at.caption))
    assert not widget(at.button, "Generate").disabled


def test_generate_lists_source_materials_except_the_syllabus(saved_project):
    (saved_project.source_dir / "ch3.txt").write_text("notes", encoding="utf-8")
    at = launch(saved_project)
    assert widget(at.multiselect, "Source materials to use").options == ["ch3.txt"]


def test_generate_review_then_save(saved_project, llm):
    at = launch(saved_project)
    widget(at.selectbox, "Week").set_value(2)
    at = click(at.run(), "Generate")

    assert_no_exception(at)
    assert any("Draft for review — outputs/quizzes/week-2-quiz.md" in s.value for s in at.subheader)
    assert not (saved_project.outputs_dir / "quizzes" / "week-2-quiz.md").exists()

    at = click(at, "Save")

    assert_no_exception(at)
    saved = saved_project.outputs_dir / "quizzes" / "week-2-quiz.md"
    assert "Draft number 1" in saved.read_text(encoding="utf-8")
    assert any(s.startswith("Saved outputs/quizzes/week-2-quiz.md.") for s in texts(at.success))


def test_regenerate_needs_confirmation_and_replaces_the_draft(saved_project, llm):
    at = click(click(launch(saved_project), "Generate"), "Regenerate")
    assert any("This makes another paid call" in w for w in texts(at.warning))
    assert len(llm) == 1

    at = click(at, "Keep this draft")
    assert "Regenerate" in {b.label for b in at.button}

    at = click(click(at, "Regenerate"), "Yes, regenerate")

    assert_no_exception(at)
    assert len(llm) == 2
    assert any("Draft number 2" in m.value for m in at.markdown)


def test_discarding_a_draft_writes_nothing(saved_project, llm):
    at = click(click(launch(saved_project), "Generate"), "Discard")
    assert at.session_state["chalk_draft"] is None
    assert not list((saved_project.outputs_dir / "quizzes").iterdir())


def test_overwriting_needs_the_checkbox(saved_project, llm):
    (saved_project.outputs_dir / "quizzes" / "week-1-quiz.md").write_text("old", encoding="utf-8")
    at = launch(saved_project)

    assert any("A quiz already exists for Week 1." in w for w in texts(at.warning))
    assert widget(at.button, "Generate").disabled
    at.checkbox[-1].check()
    assert not widget(at.run().button, "Generate").disabled


def test_rubric_waits_for_assignment_details(saved_project, llm):
    at = launch(saved_project)
    widget(at.selectbox, "Content type").set_value("rubric")
    at = at.run()
    assert "A rubric needs an assignment name and a description of the assignment." in texts(
        at.caption
    )
    assert "Generate" not in {b.label for b in at.button}

    widget(at.text_input, "Assignment name").input("Lab 3")
    widget(at.text_area, "Assignment description").input("Build two VLANs.")
    at = click(at.run(), "Generate")

    assert_no_exception(at)
    assert "Build two VLANs." in llm[0]


def test_slides_draft_is_shown_as_markdown_source(saved_project, llm):
    at = launch(saved_project)
    widget(at.selectbox, "Content type").set_value("slides")
    at = click(at.run(), "Generate")
    assert any(c.value.startswith("---\ntitle:") for c in at.code)


def test_generation_errors_are_shown_plainly(saved_project, monkeypatch):
    from chalk.errors import LLMProviderError

    def _down(prompt, system="", max_tokens=2000):
        raise LLMProviderError("Could not reach the LLM provider. Check your connection.")

    monkeypatch.setattr("chalk.generation.engine.complete", _down)
    at = click(launch(saved_project), "Generate")
    assert any("Could not reach the LLM provider" in e.value for e in at.error)


def test_export_lists_outputs_and_shows_canvas_html(saved_project):
    at = click(launch(saved_project), "Regenerate Canvas HTML and course brief")

    assert_no_exception(at)
    assert "Regenerated outputs/canvas.html and outputs/course-brief.md." in texts(at.success)
    assert at.code[0].value.startswith("<!-- Generated by Chalk")


def test_export_with_no_outputs_yet(saved_project):
    saved_project.course_brief.unlink()
    at = launch(saved_project)
    assert any(i.startswith("No outputs yet.") for i in texts(at.info))


def test_metrics_summarizes_the_eval_log(saved_project):
    log = saved_project.eval_log
    metrics.append_event(log, "generation", {"content_type": "quiz", "cost_usd": 0.0123})
    metrics.append_event(
        log,
        "rollover",
        {
            "source_term": "Fall 2026",
            "target_term": "Fall 2027",
            "source_duration_weeks": 2,
            "target_duration_weeks": 2,
            "flag_count": 1,
        },
    )
    metrics.append_event(
        log, "extraction_error", {"filename": "bad.docx", "error_type": "ProtectedFileError"}
    )

    at = launch(saved_project)

    assert_no_exception(at)
    values = {m.label: m.value for m in at.metric}
    assert values["Total AI cost"] == "$0.0123"
    assert values["Rollovers"] == "1"
    assert values["Extraction errors"] == "1"
    assert "Provider in use: OpenAI gpt-4o" in texts(at.caption)
    assert "Project cost to date: $0.0123" in at.caption[-1].value


def test_metrics_with_an_empty_log(saved_project):
    at = launch(saved_project)
    assert {"No content generated yet.", "No rollovers yet."} <= set(texts(at.caption))


def test_ferpa_notice_is_shown_where_files_are_uploaded(saved_project):
    from ui.common import FERPA_NOTICE

    at = launch(saved_project)
    assert texts(at.caption).count(FERPA_NOTICE) == 2  # Upload tab + Generate tab


def test_metrics_offers_the_evaluation_report_download(saved_project):
    at = launch(saved_project)
    assert_no_exception(at)
    assert "Download evaluation report" in [el.proto.label for el in at.get("download_button")]


def test_generate_tab_offers_a_source_material_uploader(saved_project):
    at = launch(saved_project)
    assert "Add source materials" in [e.label for e in at.expander]
    assert widget(at.button, "Add to project").disabled


def test_picker_opens_and_resets_the_demo_course(tmp_path, monkeypatch):
    monkeypatch.setattr("ui.project_picker.DEFAULT_PARENT", tmp_path)
    at = click(launch(), "Open the demo course")

    assert_no_exception(at)
    demo_root = tmp_path / "Chalk-Demo"
    assert (demo_root / "course.json").exists()
    assert at.title[0].value == "Welcome to Chalk"  # the demo has no .env yet

    at = click(launch(), "Reset the demo course")
    assert_no_exception(at)
    assert (demo_root / ".chalk-demo").exists()
