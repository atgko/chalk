"""Streamlit smoke/flow tests (PLAN.md task 51) via streamlit.testing.v1.AppTest.

AppTest runs app.py in-process, so these drive the real views against a
real project directory. File uploads aren't driven through AppTest —
the upload logic (ui.upload_view.extract_upload) is tested directly in
test_ui_helpers.py, and upload results are injected via session state.
"""

import datetime as dt
from concurrent.futures import Future
from pathlib import Path

import pytest
from freezegun import freeze_time
from streamlit.testing.v1 import AppTest

from chalk import metrics
from chalk.generation.engine import NO_SOURCES_MESSAGE
from chalk.pipeline import extract_syllabus
from chalk.project import ProjectPaths, init_project, load_course, save_course
from tests.fixtures import docx_builder, md_builder
from ui import session
from ui.common import NEEDS_COURSE_MESSAGE
from ui.session import PendingExtraction, TableChoice

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")
pytestmark = pytest.mark.usefixtures("isolated_env")


@pytest.fixture(autouse=True)
def inline_jobs(monkeypatch):
    """Run background jobs (ui/background.py) inline, so a click's result
    is there on the next run. test_background.py covers the real threads."""

    def run_now(fn, *args, **kwargs) -> Future:
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:  # noqa: BLE001 - the view reports it, as with a real thread
            future.set_exception(exc)
        return future

    monkeypatch.setattr("ui.background._submit", run_now)


def launch(paths=None, **state) -> AppTest:
    # Generous: each run is fast, but a busy machine (e.g. OneDrive syncing) can stall one.
    at = AppTest.from_file(APP_PATH, default_timeout=180)
    if paths is not None:
        at.session_state[session.PROJECT_ROOT_KEY] = str(paths.root)
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def launch_with_source(paths, **state) -> AppTest:
    """Launch with the `sourced_project` fixture's notes.txt selected on
    the Generate tab, since generation needs a source file."""
    from ui.generate_view import SOURCES_KEY

    return launch(paths, **{SOURCES_KEY: ["notes.txt"]}, **state)


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
    at = click(at, "Create project")

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


class _FakeDialog:
    """Stands in for the dialog's process: the test decides when it closes."""

    def __init__(self):
        self.started: list = []
        self.done = False
        self.folder = None
        self.cancelled = False


@pytest.fixture
def dialog(monkeypatch):
    fake = _FakeDialog()
    monkeypatch.setattr("ui.folder_picker.is_available", lambda: True)
    monkeypatch.setattr("ui.folder_picker.start", lambda initial, title: fake.started.append(title) or fake)
    monkeypatch.setattr("ui.folder_picker.finished", lambda process: process.done)
    monkeypatch.setattr("ui.folder_picker.chosen_folder", lambda process: process.folder)
    monkeypatch.setattr("ui.folder_picker.cancel", lambda process: setattr(process, "cancelled", True))
    return fake


def _browse(at: AppTest, index: int) -> AppTest:
    """Click the index-th Browse… button (0: Open, 1: Create)."""
    return [b for b in at.button if b.label == "Browse…"][index].click().run()


def _field(at: AppTest, label: str) -> str:
    return {t.label: t for t in at.text_input}[label].value


def _dialog_note_shown(at: AppTest) -> bool:
    return any("Choose a folder in the window that just opened" in i.value for i in at.info)


def test_browse_doesnt_wait_for_the_dialog(dialog):
    at = _browse(launch(), 1)

    assert_no_exception(at)
    assert dialog.started == ["Choose where to create the project"]
    assert _dialog_note_shown(at)
    assert all(b.disabled for b in at.button if b.label == "Browse…")


def test_browse_fills_the_create_it_inside_field_then_creates_there(tmp_path, dialog):
    at = _browse(launch(), 1)
    dialog.done, dialog.folder = True, str(tmp_path)
    at = at.run()

    assert _field(at, "Create it inside") == str(tmp_path)
    assert not _dialog_note_shown(at)
    assert not any(b.disabled for b in at.button if b.label == "Browse…")

    {t.label: t for t in at.text_input}["Project name"].input("IS-6640-Fall-2027")
    at = click(at, "Create project")

    assert_no_exception(at)
    assert (tmp_path / "IS-6640-Fall-2027" / "config.json").exists()


def test_browse_fills_the_project_folder_field(tmp_project, dialog):
    at = _browse(launch(), 0)
    dialog.done, dialog.folder = True, str(tmp_project.root)

    at = at.run()

    assert dialog.started == ["Choose the course project folder"]
    assert _field(at, "Project folder") == str(tmp_project.root)


def test_cancelled_browse_keeps_what_was_typed(dialog):
    at = _browse(launch(), 1)
    dialog.done = True

    at = at.run()

    assert_no_exception(at)
    assert _field(at, "Create it inside").endswith("projects")
    assert not _dialog_note_shown(at)


def test_cancel_button_closes_an_open_dialog(dialog):
    at = click(_browse(launch(), 1), "Cancel")

    assert_no_exception(at)
    assert dialog.cancelled
    assert not _dialog_note_shown(at)
    assert not any(b.disabled for b in at.button if b.label == "Browse…")


def test_a_dialog_that_cant_open_says_to_type_the_path(monkeypatch):
    monkeypatch.setattr("ui.folder_picker.is_available", lambda: True)
    monkeypatch.setattr("ui.folder_picker.start", lambda initial, title: None)

    at = _browse(launch(), 0)

    assert_no_exception(at)
    assert any("couldn't open" in w.value for w in at.warning)


def test_no_browse_buttons_when_the_folder_dialog_is_unavailable(monkeypatch):
    monkeypatch.setattr("ui.folder_picker.is_available", lambda: False)

    at = launch()

    assert "Browse…" not in {b.label for b in at.button}
    assert {"Open project", "Create project"} <= {b.label for b in at.button}


def test_opening_a_folder_that_is_not_a_project_shows_a_plain_error(tmp_path):
    at = launch()
    {t.label: t for t in at.text_input}["Project folder"].input(str(tmp_path))
    at = click(at, "Open project")
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
        "Drafts",
        "Export",
        "Grading Assistant",
        "Metrics",
        "Settings",
    ]
    assert "Provider: Not configured" in at.caption[-1].value


def test_jump_to_opens_the_generate_tab_with_the_content_type_selected(saved_project):
    at = launch(saved_project)

    widget(at.selectbox, "Jump to").select("generate-rubric")
    at = at.run()

    assert_no_exception(at)
    assert at.session_state[session.ACTIVE_TAB_KEY] == "Generate"
    assert widget(at.selectbox, "Content type").value == "rubric"
    assert widget(at.selectbox, "Jump to").value is None


def test_jump_to_opens_a_tab_without_a_course(project):
    at = launch(project)

    widget(at.selectbox, "Jump to").select("grade-submission")
    at = at.run()

    assert_no_exception(at)
    assert at.session_state[session.ACTIVE_TAB_KEY] == "Grading Assistant"


def test_first_run_setup_validates_then_saves_for_every_course(tmp_project, monkeypatch):
    from chalk.saved_provider import read_saved_provider
    from ui.provider_form import SAVED_EVERYWHERE

    calls = []
    monkeypatch.setattr(
        "chalk.config.complete", lambda prompt, max_tokens=5: calls.append(prompt) or {}
    )
    at = launch(tmp_project)
    at.radio[0].set_value("Local model (Ollama)")
    at = click(at.run(), "Test connection and continue")

    assert_no_exception(at)
    assert calls
    assert read_saved_provider()["LLM_BASE_URL"] == "http://localhost:11434/v1"
    assert not tmp_project.env.exists()  # nothing in a plain file
    assert SAVED_EVERYWHERE in texts(at.success)
    assert "Provider: Local model llama3.1:70b" in at.caption[-1].value


def test_a_new_course_skips_setup_once_a_key_is_saved(tmp_project):
    from chalk.saved_provider import save_provider

    save_provider({"LLM_PROVIDER": "openai", "LLM_API_KEY": "sk-saved", "LLM_BASE_URL": "", "LLM_MODEL": "gpt-4o"})
    at = launch(tmp_project)

    assert_no_exception(at)
    assert "Test connection and continue" not in {b.label for b in at.button}
    assert "Provider: OpenAI gpt-4o" in at.caption[-1].value


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

    from chalk.config import read_env
    from chalk.saved_provider import read_saved_provider
    from ui.provider_form import SAVED_EVERYWHERE

    assert_no_exception(at)
    saved = read_saved_provider()
    assert saved["LLM_API_KEY"] == "sk-test"  # the course's key, kept
    assert saved["LLM_MODEL"] == "gpt-4o-mini"
    assert read_env(project.env) == {}  # moved out of the course's plain-text file
    assert SAVED_EVERYWHERE in texts(at.success)


# ---- Tab gating --------------------------------------------------------------------


def test_gated_tabs_redirect_until_a_course_exists(project):
    at = launch(project)
    assert_no_exception(at)
    assert texts(at.info).count(NEEDS_COURSE_MESSAGE) == 4
    assert "course.json" not in NEEDS_COURSE_MESSAGE  # professors don't know the file
    [style] = at.get("html")
    for position in (3, 4, 6, 8):  # Rollover, Generate, Export, Metrics are dimmed
        assert f'[data-testid="stTab"]:nth-of-type({position}) {{opacity: 0.45;}}' in style.proto.body
    assert "nth-of-type(1) {opacity" not in style.proto.body


def test_go_to_upload_opens_the_upload_tab(project):
    at = launch(project, **{session.ACTIVE_TAB_KEY: "Generate"})
    [button] = [b for b in at.button if b.key == "needs-course-Generate"]
    at = button.click().run()
    assert_no_exception(at)
    assert at.session_state[session.ACTIVE_TAB_KEY] == "Upload"


def test_tabs_are_not_dimmed_once_a_course_is_saved(saved_project):
    [style] = launch(saved_project).get("html")
    assert "opacity" not in style.proto.body


# ---- Switching course --------------------------------------------------------------


def test_switch_course_goes_back_to_the_projects_list(saved_project):
    at = launch(saved_project, chalk_course_state="kept for this course")
    at = click(at, "All courses")
    assert_no_exception(at)
    assert "Open a course project" in [h.value for h in at.subheader]
    assert "chalk_course_state" not in at.session_state  # nothing carries over to the next course
    assert session.PROJECT_ROOT_KEY not in at.session_state


def test_switch_course_waits_for_running_ai_work(saved_project):
    from concurrent.futures import Future

    from ui import background

    running = background.Job("Generating a draft", Future(), 0.0, tab="Generate")
    at = launch(saved_project, **{background._JOBS_KEY: {"generate": running}})
    [button] = [b for b in at.button if b.label == "All courses"]
    assert button.disabled


def test_unreadable_course_json_is_reported_not_raised(project):
    project.course_json.write_text("{not json", encoding="utf-8")
    at = launch(project)
    assert_no_exception(at)
    assert "couldn't read this course's saved details (course.json)" in at.error[0].value


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

    assert any("Term and schedule don't match" in warning for warning in texts(at.warning))
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
    assert any("Multiple possible schedule tables" in warning for warning in texts(at.warning))

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

def test_a_failed_read_is_cleared_once_a_read_succeeds(project, tmp_path):
    bad = TableChoice(md_builder.build_syllabus_with_no_schedule_table(tmp_path / "bad.md"), ["a", "b"])
    at = click(launch(project, chalk_table_choice=bad), "Use this table")
    assert at.error
    at = at.run()
    assert at.error  # stays while the instructor decides what to try next

    good = md_builder.build_syllabus_with_multiple_candidate_tables(tmp_path / "two.md")
    at.session_state["chalk_table_choice"] = TableChoice(good, ["Week | Dates / 1 | first", "b"])
    at = click(at.run(), "Use this table")
    assert at.session_state[session.ACTIVE_TAB_KEY] == "Review"
    at.session_state[session.ACTIVE_TAB_KEY] = "Upload"
    at = at.run()

    assert_no_exception(at)
    assert not at.error


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
    assert "Saved the course and updated the course brief." in texts(at.success)


def test_discard_drops_the_unsaved_extraction_and_keeps_the_saved_course(saved_project, tmp_path):
    saved_title = load_course(saved_project).course.title
    pending = _pending(saved_project, tmp_path, docx_builder.build_minimal_syllabus, "new.docx")
    at = launch(saved_project, chalk_pending_extraction=pending)
    assert "Newly extracted — not saved yet." in texts(at.caption)

    at = click(at, "Discard")

    assert_no_exception(at)
    assert at.session_state[session._PENDING_EXTRACTION_KEY] is None
    assert "Discarded the new extraction. The saved course is unchanged." in texts(at.success)
    assert "Showing the saved course." in texts(at.caption)
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

    assert any("Credits must be a number like 3 or 1.5" in e for e in texts(at.error))
    assert load_course(project).course.credits is None


def test_review_accepts_one_and_a_half_credits(project, tmp_path):
    _save_course_missing_details(project, tmp_path)
    at = launch(project)

    widget(at.text_input, "Credits").set_value("1.5")
    at = click(at.run(), "Confirm and save")

    assert_no_exception(at)
    assert load_course(project).course.credits == 1.5


def test_review_shows_the_saved_course_when_nothing_is_pending(saved_project):
    at = launch(saved_project)
    assert "Showing the saved course." in texts(at.caption)
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

    def _complete(prompt, system="", max_tokens=2000, on_text=None):
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


def test_generate_without_source_materials_asks_for_one(saved_project):
    at = launch(saved_project)
    assert "No source materials added yet" in " ".join(texts(at.caption))
    assert NO_SOURCES_MESSAGE in texts(at.info)
    assert "Generate" not in {b.label for b in at.button}


def test_generate_waits_until_a_source_is_selected(sourced_project):
    at = launch(sourced_project)
    assert NO_SOURCES_MESSAGE in texts(at.info)
    assert "Generate" not in {b.label for b in at.button}

    widget(at.multiselect, "Source materials to use").set_value(["notes.txt"])
    at = at.run()

    assert any(c.startswith("Estimated cost: up to ~$") for c in texts(at.caption))
    assert not widget(at.button, "Generate").disabled


def test_generate_lists_source_materials_except_the_syllabus(saved_project):
    (saved_project.source_dir / "ch3.txt").write_text("notes", encoding="utf-8")
    at = launch(saved_project)
    assert widget(at.multiselect, "Source materials to use").options == ["ch3.txt"]


def test_generate_review_then_save(sourced_project, llm):
    at = launch_with_source(sourced_project)
    widget(at.selectbox, "Week").set_value(2)
    at = click(at.run(), "Generate")

    assert_no_exception(at)
    assert any("Draft for review — outputs/quizzes/week-2-quiz.md" in s.value for s in at.subheader)
    assert not (sourced_project.outputs_dir / "quizzes" / "week-2-quiz.md").exists()

    at = click(at, "Save")

    assert_no_exception(at)
    saved = sourced_project.outputs_dir / "quizzes" / "week-2-quiz.md"
    assert "Draft number 1" in saved.read_text(encoding="utf-8")
    assert any(s.startswith("Saved outputs/quizzes/week-2-quiz.md.") for s in texts(at.success))


def test_a_quiz_draft_can_be_exported_as_word_or_pdf(sourced_project, llm):
    at = click(launch_with_source(sourced_project), "Generate")

    assert_no_exception(at)
    assert widget(at.selectbox, "File type").options == ["Word (.docx)", "PDF (.pdf)", "Markdown (.md)"]
    widget(at.selectbox, "File type").set_value("PDF (.pdf)")
    assert_no_exception(at.run())


def test_slide_drafts_have_no_document_export(saved_project):
    (saved_project.outputs_dir / "slides" / "week-1-slides.md").write_text("---\ntitle: W1\n---\n", encoding="utf-8")
    at = launch(saved_project)
    assert_no_exception(at)
    assert draft_titles(at) == ["Week 1 — Slides"]
    assert "File type" not in [s.label for s in at.selectbox]
def test_mixed_quiz_asks_for_the_split_and_sends_it(sourced_project, llm):
    at = launch_with_source(sourced_project)
    assert "Multiple-choice questions" not in {n.label for n in at.number_input}
    widget(at.number_input, "Multiple choice").set_value(4)
    widget(at.number_input, "Short answer").set_value(1)
    at = click(at.run(), "Generate")

    assert_no_exception(at)
    assert "Generate 5 questions in mixed (exactly 4 multiple choice and 1 short answer) format." in llm[0]


@pytest.mark.parametrize(
    ("quiz_format", "count_label", "hidden"),
    [
        ("short answer", "Short-answer questions", {"Multiple choice", "Short answer"}),
        ("multiple choice", "Multiple-choice questions", {"Multiple choice", "Short answer"}),
    ],
)
def test_single_format_quiz_asks_for_one_count_named_for_it(saved_project, quiz_format, count_label, hidden):
    at = launch(saved_project)
    widget(at.selectbox, "Format").set_value(quiz_format)
    at = at.run()
    labels = {n.label for n in at.number_input}
    assert count_label in labels
    assert not labels & hidden


def test_regenerate_needs_confirmation_and_replaces_the_draft(sourced_project, llm):
    at = click(click(launch_with_source(sourced_project), "Generate"), "Regenerate")
    assert any("This makes another paid call" in w for w in texts(at.warning))
    assert len(llm) == 1

    at = click(at, "Keep this draft")
    assert "Regenerate" in {b.label for b in at.button}

    at = click(click(at, "Regenerate"), "Yes, regenerate")

    assert_no_exception(at)
    assert len(llm) == 2
    assert any("Draft number 2" in m.value for m in at.markdown)


def test_discarding_a_draft_writes_nothing(sourced_project, llm):
    at = click(click(launch_with_source(sourced_project), "Generate"), "Discard")
    assert at.session_state["chalk_draft"] is None
    assert not list((sourced_project.outputs_dir / "quizzes").iterdir())


def test_overwriting_needs_the_checkbox(sourced_project, llm):
    (sourced_project.outputs_dir / "quizzes" / "week-1-quiz.md").write_text("old", encoding="utf-8")
    at = launch_with_source(sourced_project)

    assert any("A quiz already exists for Week 1." in w for w in texts(at.warning))
    assert widget(at.button, "Generate").disabled
    widget(at.checkbox, "Yes — archive the old version and generate a new one").check()
    assert not widget(at.run().button, "Generate").disabled


def draft_titles(at: AppTest) -> list[str]:
    """Drafts-tab expanders (the Generate tab has one of its own)."""
    return [e.label for e in at.expander if " — " in e.label]


def test_drafts_tab_explains_when_nothing_is_saved(saved_project):
    at = launch(saved_project)
    assert "No saved drafts yet. Generate one on the Generate tab and click Save." in texts(at.info)


def test_a_saved_draft_appears_on_the_drafts_tab(sourced_project, llm):
    at = click(click(launch_with_source(sourced_project), "Generate"), "Save")
    (sourced_project.outputs_dir / "quizzes" / ".archive").mkdir()
    (sourced_project.outputs_dir / "quizzes" / ".archive" / "week-1-quiz-20261001-101500.md").write_text(
        "old", encoding="utf-8"
    )
    at = at.run()

    assert_no_exception(at)
    assert draft_titles(at) == ["Week 1 — Quiz"]
    assert any("Draft number 1" in m.value for m in at.markdown)
    assert any(
        "outputs/quizzes/week-1-quiz.md · 1 earlier version in .archive/" in c for c in texts(at.caption)
    )


def test_drafts_tab_filters_by_type(saved_project):
    out = saved_project.outputs_dir
    (out / "quizzes" / "week-2-quiz.md").write_text("quiz", encoding="utf-8")
    (out / "discussions" / "week-2-discussion.md").write_text("talk", encoding="utf-8")
    at = launch(saved_project)
    assert draft_titles(at) == ["Week 2 — Quiz", "Week 2 — Discussion prompts"]

    widget(at.selectbox, "Show").set_value("Discussion prompts")
    at = at.run()

    assert draft_titles(at) == ["Week 2 — Discussion prompts"]


def test_deleting_a_draft_needs_the_checkbox_and_archives_it(saved_project):
    quiz = saved_project.outputs_dir / "quizzes" / "week-2-quiz.md"
    quiz.write_text("quiz", encoding="utf-8")
    at = launch(saved_project)
    assert widget(at.button, "Delete").disabled

    widget(at.checkbox, "Yes — delete this draft (it moves to .archive/)").check()
    at = click(at.run(), "Delete")

    assert_no_exception(at)
    assert not quiz.exists()
    assert len(list((quiz.parent / ".archive").iterdir())) == 1
    assert draft_titles(at) == []
    assert "No saved drafts yet. Generate one on the Generate tab and click Save." in texts(at.info)


def test_assignment_drafts_download_as_word_by_default(saved_project):
    (saved_project.outputs_dir / "assignments" / "lab-3-assignment.md").write_text(
        "# Lab 3\n\nBuild a VLAN.", encoding="utf-8"
    )
    at = launch(saved_project)

    assert_no_exception(at)
    assert draft_titles(at) == ["Lab 3 — Assignment creator / enhancer"]
    assert widget(at.selectbox, "File type").value == "Word (.docx)"


def test_rubric_waits_for_assignment_details(sourced_project, llm):
    at = launch_with_source(sourced_project)
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


def test_slides_draft_is_shown_as_markdown_source(sourced_project, llm):
    at = launch_with_source(sourced_project)
    widget(at.selectbox, "Content type").set_value("slides")
    at = click(at.run(), "Generate")
    assert any(c.value.startswith("---\ntitle:") for c in at.code)


def test_generation_errors_are_shown_plainly(sourced_project, monkeypatch):
    from chalk.errors import LLMProviderError

    def _down(prompt, system="", max_tokens=2000, on_text=None):
        raise LLMProviderError("Could not reach the LLM provider. Check your connection.")

    monkeypatch.setattr("chalk.generation.engine.complete", _down)
    at = click(launch_with_source(sourced_project, **{session.ACTIVE_TAB_KEY: "Generate"}), "Generate")
    assert any("Could not reach the LLM provider" in e.value for e in at.error)


def test_export_lists_outputs_and_shows_canvas_html(saved_project):
    at = click(launch(saved_project), "Regenerate Canvas HTML and course brief")

    assert_no_exception(at)
    assert "Regenerated outputs/canvas.html and outputs/course-brief.md." in texts(at.success)
    assert at.code[0].value.startswith("<!-- Generated by Chalk")
    steps = [m.value for m in at.markdown if "Update Syllabus" in m.value]
    assert steps and "**View**, then **HTML Editor**" in steps[0]
    [preview] = [e for e in at.expander if e.label == "Preview: how it will look in Canvas"]
    assert "Detailed Syllabus" in preview.children[0].proto.body


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
    assert values["AI cost this month"] == "$0.0123"
    assert "All-time AI cost: $0.0123" in texts(at.caption)
    assert values["Rollovers"] == "1"
    assert values["Extraction errors"] == "1"
    assert "Provider in use: OpenAI gpt-4o" in texts(at.caption)
    assert "Project cost to date: $0.0123" in at.caption[-1].value


def test_metrics_compares_this_months_cost_with_last_month(saved_project):
    log = saved_project.eval_log
    with freeze_time("2026-09-15T12:00:00+00:00"):
        metrics.append_event(log, "generation", {"content_type": "quiz", "cost_usd": 0.0100})
    with freeze_time("2026-10-15T12:00:00+00:00"):
        metrics.append_event(log, "generation", {"content_type": "quiz", "cost_usd": 0.0250})
        at = launch(saved_project)

    assert_no_exception(at)
    [this_month] = [m for m in at.metric if m.label == "AI cost this month"]
    assert this_month.value == "$0.0250"
    assert this_month.delta == "+$0.0150 vs last month"
    assert "All-time AI cost: $0.0350" in texts(at.caption)
    [monthly] = [d for d in at.dataframe if "Avg cost / generation" in d.value.columns]
    assert monthly.value["Month"].tolist() == ["2026-10", "2026-09"]


def test_metrics_with_an_empty_log(saved_project):
    at = launch(saved_project)
    assert {"No content generated yet.", "No AI costs yet.", "No rollovers yet."} <= set(texts(at.caption))


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


def test_generate_defaults_the_course_level_from_the_course_number(sourced_project, llm):
    at = launch_with_source(sourced_project)
    level = widget(at.selectbox, "Course level")
    assert level.value == "upper-division"  # IS 4490

    level.set_value("graduate")
    at = click(at.run(), "Generate")

    assert "COURSE LEVEL: graduate." in llm[-1]


def test_an_assignment_can_include_an_ai_use_task(sourced_project, llm):
    at = launch_with_source(sourced_project)
    widget(at.selectbox, "Content type").set_value("assignment")
    at = at.run()
    widget(at.text_input, "Assignment name").input("Design Brief")
    widget(at.text_area, "What should students learn or demonstrate?").input("Defend a design.")
    widget(at.checkbox, "Include a task where students use AI as part of their learning").check()
    at = click(at.run(), "Generate")

    assert "AI-USE COMPONENT" in llm[-1]


# ---- Launch screen: your projects, and creating one that exists ---------------------------


@pytest.fixture
def projects_folder(tmp_path, monkeypatch):
    """The launch screen's default projects/ folder, empty to start."""
    folder = tmp_path / "projects"
    folder.mkdir()
    monkeypatch.setattr("ui.project_picker.DEFAULT_PARENT", folder)
    return folder


def test_your_projects_lists_and_opens_projects_in_the_projects_folder(projects_folder):
    init_project(projects_folder, "IS-4490-Fall-2027")
    init_project(projects_folder, "IS-6640-Fall-2027")
    at = launch()

    choice = widget(at.selectbox, "Your projects")
    assert sorted(choice.options) == ["IS-4490-Fall-2027", "IS-6640-Fall-2027"]
    second = choice.options[1]
    choice.select_index(1)
    at = click(at, "Open")

    assert_no_exception(at)
    assert any(f"Opened project {second}." in s.value for s in at.success)


def test_no_project_list_when_the_projects_folder_is_empty(projects_folder):
    at = launch()
    assert "Your projects" not in {s.label for s in at.selectbox}


def test_creating_a_project_that_exists_offers_to_open_it(projects_folder):
    init_project(projects_folder, "IS-6640-Fall-2027")
    at = launch()
    widget(at.text_input, "Project name").input("IS-6640-Fall-2027")

    at = click(at, "Create project")

    assert any("already a course project named IS-6640-Fall-2027" in w.value for w in at.warning)
    at = click(at, "Open IS-6640-Fall-2027")
    assert_no_exception(at)
    assert any("Opened project IS-6640-Fall-2027" in s.value for s in at.success)


def test_choosing_another_name_dismisses_the_offer(projects_folder):
    init_project(projects_folder, "IS-6640-Fall-2027")
    at = launch()
    widget(at.text_input, "Project name").input("IS-6640-Fall-2027")
    at = click(click(at, "Create project"), "Choose another name")

    assert not any("already a course project" in w.value for w in at.warning)
    assert "Open IS-6640-Fall-2027" not in {b.label for b in at.button}


# ---- A schedule with no dates -------------------------------------------------------


def test_review_asks_for_week1_of_an_undated_schedule_and_redates_it(project, tmp_path):
    import datetime as dt

    from tests.test_undated_schedule import _outline_syllabus

    pending = _pending(project, tmp_path, lambda path: _outline_syllabus(path, meetings=3), "outline.docx")
    at = launch(project, chalk_pending_extraction=pending)
    assert any("schedule has no dates" in i for i in texts(at.info))
    [week1] = at.date_input
    assert week1.value == dt.date(2026, 8, 24)  # Fall 2026's first day, from the calendar

    week1.set_value(dt.date(2026, 8, 31))
    at = click(at.run(), "Confirm and save")

    assert_no_exception(at)
    weeks = [w.date for w in load_course(project).weeks if not w.is_break]
    assert weeks == [dt.date(2026, 8, 31), dt.date(2026, 9, 7), dt.date(2026, 9, 14)]


def test_review_assumes_an_undated_class_meets_through_a_break_it_doesnt_mention(project, tmp_path):
    from tests.test_undated_schedule import _outline_syllabus

    pending = _pending(project, tmp_path, _outline_syllabus, "outline.docx")  # 10 meetings, crosses Fall Break
    at = launch(project, chalk_pending_extraction=pending)
    [no_class] = at.checkbox
    assert no_class.label == "No class during Fall Break (10/10 - 10/18)"
    assert no_class.value is False
    assert not any("Fall Break" in str(row) for row in at.dataframe[-1].value.values.tolist())

    no_class.check()
    at = click(at.run(), "Confirm and save")

    assert_no_exception(at)
    assert [w.label for w in load_course(project).weeks if w.is_break] == ["Fall Break (10/10 - 10/18)"]


def test_review_doesnt_ask_for_week1_of_a_dated_schedule(project, tmp_path):
    pending = _pending(project, tmp_path, md_builder.build_minimal_syllabus, "s.md")
    assert not launch(project, chalk_pending_extraction=pending).date_input


# ---- Sessions -----------------------------------------------------------------------


def test_rollover_into_a_later_session_sets_week1_and_the_length(saved_project):
    import datetime as dt

    from chalk.sessions import SessionSpan

    at = launch(saved_project)
    widget(at.selectbox, "Session").set_value(SessionSpan(2, 3))
    at = at.run()
    assert "Session 2 of Fall 2027 starts Monday, September 27." in texts(at.caption)
    assert widget(at.number_input, "Duration (weeks)").value == 10

    at = click(at, "Preview rollover")

    assert_no_exception(at)
    plan = at.session_state["chalk_rollover_plan"].plan
    first = next(w for w in plan.rolled_over.weeks if not w.is_break)
    assert first.date == dt.date(2027, 9, 27)
    assert plan.rolled_over.course.duration_weeks == 10


def test_an_undated_course_can_start_in_a_later_session(project, tmp_path):
    import datetime as dt

    from chalk.sessions import SessionSpan
    from tests.test_undated_schedule import _outline_syllabus

    pending = _pending(project, tmp_path, lambda path: _outline_syllabus(path, meetings=10), "outline.docx")
    at = launch(project, chalk_pending_extraction=pending)
    assert widget(at.selectbox, "Session").value == SessionSpan(1, 2)  # 10 meetings

    widget(at.selectbox, "Session").set_value(SessionSpan(2, 3))
    at = at.run()
    [week1] = at.date_input
    assert week1.value == dt.date(2026, 9, 28)  # Session 2 of Fall 2026
    assert tables_first_date(at) == "Sep 28 (9/28)"


def tables_first_date(at) -> str:
    """The Date column of the Review tab's first week row."""
    [weeks] = [frame for frame in at.dataframe if "Date" in frame.value.columns]
    return weeks.value["Date"].iloc[0]


def test_a_summer_rollover_offers_10_or_12_weeks(saved_project):
    import datetime as dt

    at = launch(saved_project)
    widget(at.selectbox, "Target term").set_value("Summer 2027")
    at = at.run()
    from chalk.sessions import summer_length

    length = widget(at.selectbox, "Summer length")
    assert length.options == ["Full summer term (12 weeks)", "10 weeks"]
    assert widget(at.number_input, "Duration (weeks)").value == 10  # the saved course has 2 weeks

    length.set_value(summer_length(12))
    at = click(at.run(), "Preview rollover")

    assert_no_exception(at)
    plan = at.session_state["chalk_rollover_plan"].plan
    assert plan.rolled_over.course.duration_weeks == 12
    assert next(w for w in plan.rolled_over.weeks if not w.is_break).date == dt.date(2027, 5, 17)
