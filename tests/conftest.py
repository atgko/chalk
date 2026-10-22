"""Shared pytest fixtures for the Chalk test suite.

Fixtures are added incrementally as each milestone introduces the objects
they need: sample_course_data, tmp_project_dir, synthetic_docx_factory,
synthetic_md_factory, mock_llm_client, frozen_time. See PLAN.md Section 5
("Test Strategy") for the full fixture-to-task map.
"""

import keyring
import pytest
from keyring.backend import KeyringBackend

from chalk.pipeline import extract_syllabus, save_reviewed_course
from chalk.project import init_project
from tests.fixtures import md_builder

_ENV_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")


class MemoryKeyring(KeyringBackend):
    """A credential store that lives in memory, so tests never touch the
    real Windows Credential Manager or macOS Keychain."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.passwords.get((service, username))

    def set_password(self, service, username, password):
        self.passwords[(service, username)] = password

    def delete_password(self, service, username):
        self.passwords.pop((service, username), None)


@pytest.fixture(autouse=True)
def memory_keyring():
    """Every test gets an empty in-memory credential store."""
    previous = keyring.get_keyring()
    store = MemoryKeyring()
    keyring.set_keyring(store)
    yield store
    keyring.set_keyring(previous)


@pytest.fixture
def tmp_project(tmp_path):
    """A freshly `init`-ed course project under tmp_path, seeded from the
    real bundled resources (config.json, calendars.json)."""
    return init_project(tmp_path, "IS-6640-Test")


# ---- Streamlit app tests (test_app.py, test_background.py) -------------------


@pytest.fixture
def isolated_env(monkeypatch):
    """The app loads the project's .env into os.environ; register every
    provider variable with monkeypatch so each test's changes are undone.
    The app tests apply it to every test with `pytestmark`."""
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
