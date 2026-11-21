"""The main educational framework, chosen once in Settings → More settings."""

import pytest

from chalk.errors import ChalkError, GenerationError
from chalk.generation.educational_frameworks import (
    DEFAULT_FRAMEWORK,
    FRAMEWORKS,
    framework_guidance,
    load_main_framework,
    save_main_framework,
    settings_path,
)


def test_no_saved_choice_means_the_default():
    assert not settings_path().exists()
    assert load_main_framework() == DEFAULT_FRAMEWORK


def test_a_saved_choice_is_read_back(courses_folder):
    save_main_framework("fink")

    assert settings_path() == courses_folder / "Chalk framework.json"
    assert load_main_framework() == "fink"


@pytest.mark.parametrize("content", ["not json", '["a list"]', '{"framework": "made_up"}'])
def test_a_damaged_or_unknown_choice_means_the_default(tmp_path, content):
    path = tmp_path / "framework.json"
    path.write_text(content, encoding="utf-8")

    assert load_main_framework(path) == DEFAULT_FRAMEWORK


def test_saving_an_unknown_framework_is_refused(tmp_path):
    path = tmp_path / "framework.json"
    with pytest.raises(GenerationError):
        save_main_framework("made_up", path)
    assert not path.exists()


def test_a_failed_save_says_where(tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("", encoding="utf-8")

    with pytest.raises(ChalkError, match="couldn't save the framework choice"):
        save_main_framework("fink", blocker / "framework.json")


def test_every_framework_but_none_gives_guidance():
    assert framework_guidance("none") == ""
    for framework in FRAMEWORKS[1:]:
        assert "EDUCATIONAL DESIGN GUIDANCE" in framework_guidance(framework, "A memo")
    with pytest.raises(GenerationError):
        framework_guidance("made_up")
