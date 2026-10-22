import json
import os

import pytest

from chalk import saved_provider
from chalk.config import (
    ProviderSettings,
    adopt_project_provider,
    apply_provider_env,
    choice_for_env,
    describe_provider,
    effective_env,
    env_is_configured,
    load_config,
    model_options,
    provider_settings,
    read_env,
    validate_and_save_provider,
    validate_provider,
    write_provider_env,
)
from chalk.errors import ChalkError, LLMProviderError


def test_read_env_returns_empty_dict_for_missing_file(tmp_path):
    assert read_env(tmp_path / ".env") == {}


def test_write_provider_env_creates_file_with_expected_keys(tmp_path):
    env_path = tmp_path / ".env"
    write_provider_env(
        env_path,
        provider="openai",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
    )

    values = read_env(env_path)
    assert values["LLM_PROVIDER"] == "openai"
    assert values["LLM_API_KEY"] == "sk-test"
    assert values["LLM_BASE_URL"] == "https://api.openai.com/v1"
    assert values["LLM_MODEL"] == "gpt-4o"


def test_write_provider_env_overwrites_existing_values(tmp_path):
    env_path = tmp_path / ".env"
    write_provider_env(env_path, provider="openai", api_key="sk-old", base_url="", model="gpt-4o")
    write_provider_env(
        env_path,
        provider="anthropic",
        api_key="sk-ant-new",
        base_url="",
        model="claude-sonnet-5",
    )

    values = read_env(env_path)
    assert values["LLM_PROVIDER"] == "anthropic"
    assert values["LLM_API_KEY"] == "sk-ant-new"
    assert values["LLM_MODEL"] == "claude-sonnet-5"


def test_env_is_configured_false_when_file_missing(tmp_path):
    assert env_is_configured(tmp_path / ".env") is False


def test_env_is_configured_false_when_a_required_key_is_blank(tmp_path):
    env_path = tmp_path / ".env"
    write_provider_env(env_path, provider="openai", api_key="", base_url="", model="gpt-4o")
    assert env_is_configured(env_path) is False


def test_env_is_configured_true_once_required_keys_are_set(tmp_path):
    env_path = tmp_path / ".env"
    write_provider_env(env_path, provider="openai", api_key="sk-test", base_url="", model="gpt-4o")
    assert env_is_configured(env_path) is True


def test_load_config_reads_json_file(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"institution": "University of Utah"}), encoding="utf-8")

    config = load_config(config_path)
    assert config["institution"] == "University of Utah"


def test_load_config_fills_in_provider_rates_an_older_project_is_missing(tmp_path):
    config_path = tmp_path / "config.json"
    old_project = {"cost_rates": {"openai": {"gpt-custom": {"input_per_1k": 1, "output_per_1k": 2}}}}
    config_path.write_text(json.dumps(old_project), encoding="utf-8")

    rates = load_config(config_path)["cost_rates"]

    assert rates["openai"] == {"gpt-custom": {"input_per_1k": 1, "output_per_1k": 2}}
    assert "gemini-3.5-flash" in rates["gemini"]


def test_validate_provider_succeeds_and_restores_previous_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "sk-original")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    monkeypatch.setattr(
        "chalk.config.complete",
        lambda prompt, max_tokens=5: {"text": "OK", "input_tokens": 5, "output_tokens": 1},
    )

    validate_provider("anthropic", "sk-ant-candidate", "", "claude-sonnet-5")

    # The candidate config must never leak into the real environment.
    assert os.environ["LLM_PROVIDER"] == "openai"
    assert os.environ["LLM_API_KEY"] == "sk-original"
    assert "LLM_BASE_URL" not in os.environ


def test_validate_provider_propagates_the_error_and_still_restores_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "sk-original")

    def _boom(prompt, max_tokens=5):
        raise LLMProviderError("API key was not accepted. Check your key and try again.")

    monkeypatch.setattr("chalk.config.complete", _boom)

    with pytest.raises(LLMProviderError):
        validate_provider("openai", "sk-bad", "", "gpt-4o")

    assert os.environ["LLM_API_KEY"] == "sk-original"


def test_validate_provider_cleans_up_env_vars_that_were_previously_unset(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setattr(
        "chalk.config.complete",
        lambda prompt, max_tokens=5: {"text": "OK", "input_tokens": 5, "output_tokens": 1},
    )

    validate_provider("openai", "sk-test", "http://localhost:11434/v1", "llama3.1:70b")

    assert "LLM_BASE_URL" not in os.environ


# ---- Provider form helpers ------------------------------------------------------


def test_openai_settings_use_the_official_base_url():
    settings = provider_settings("OpenAI", api_key=" sk-1 ", model="gpt-4o")
    assert settings == ProviderSettings("openai", "sk-1", "https://api.openai.com/v1", "gpt-4o")


def test_anthropic_settings_leave_base_url_blank():
    settings = provider_settings("Anthropic Claude", api_key="sk-ant", model="claude-sonnet-5")
    assert settings == ProviderSettings("anthropic", "sk-ant", "", "claude-sonnet-5")


def test_gemini_settings_use_googles_openai_compatible_url():
    settings = provider_settings("Google Gemini", api_key="AIza", model="gemini-3.5-flash")
    assert settings == ProviderSettings(
        "gemini", "AIza", "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-3.5-flash"
    )


def test_ollama_settings_fill_in_prd_defaults():
    settings = provider_settings("Local model (Ollama)")
    assert settings == ProviderSettings("openai", "ollama", "http://localhost:11434/v1", "llama3.1:70b")


def test_ollama_settings_keep_what_the_instructor_typed():
    settings = provider_settings("Local model (Ollama)", base_url="http://vm:11434/v1", model="qwen")
    assert (settings.base_url, settings.model) == ("http://vm:11434/v1", "qwen")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"model": "gpt-4o"}, "Paste your OpenAI API key"), ({"api_key": "sk"}, "Choose a model")],
)
def test_hosted_providers_require_key_and_model(kwargs, message):
    with pytest.raises(ChalkError, match=message):
        provider_settings("OpenAI", **kwargs)


def test_unknown_choice_is_a_programming_error():
    with pytest.raises(ValueError):
        provider_settings("Mistral", api_key="x", model="y")


@pytest.mark.parametrize(
    ("env", "choice"),
    [
        ({}, "OpenAI"),
        ({"LLM_PROVIDER": "openai", "LLM_BASE_URL": "https://api.openai.com/v1"}, "OpenAI"),
        ({"LLM_PROVIDER": "ANTHROPIC"}, "Anthropic Claude"),
        ({"LLM_PROVIDER": "gemini", "LLM_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/"},
         "Google Gemini"),
        ({"LLM_PROVIDER": "openai", "LLM_BASE_URL": "http://localhost:11434/v1"}, "Local model (Ollama)"),
    ],
)
def test_choice_for_env(env, choice):
    assert choice_for_env(env) == choice


def test_model_options_come_from_cost_rates():
    config = {
        "cost_rates": {
            "openai": {"gpt-4o": {}, "gpt-4o-mini": {}},
            "anthropic": {"claude-sonnet-5": {}},
            "gemini": {"gemini-3.5-flash-lite": {}},
        }
    }
    assert model_options(config, "OpenAI") == ["gpt-4o", "gpt-4o-mini"]
    assert model_options(config, "Google Gemini") == ["gemini-3.5-flash-lite"]
    assert model_options(config, "Anthropic Claude") == ["claude-sonnet-5"]
    assert model_options(config, "Local model (Ollama)") == []
    assert model_options({}, "OpenAI") == []


@pytest.mark.parametrize(
    ("env", "text"),
    [
        ({}, "Not configured"),
        ({"LLM_PROVIDER": "openai", "LLM_API_KEY": "k", "LLM_MODEL": "gpt-4o"}, "OpenAI gpt-4o"),
        (
            {"LLM_PROVIDER": "anthropic", "LLM_API_KEY": "k", "LLM_MODEL": "claude-sonnet-5"},
            "Anthropic claude-sonnet-5",
        ),
        (
            {"LLM_PROVIDER": "gemini", "LLM_API_KEY": "k", "LLM_MODEL": "gemini-3.5-flash"},
            "Gemini gemini-3.5-flash",
        ),
        (
            {"LLM_PROVIDER": "openai", "LLM_API_KEY": "ollama", "LLM_BASE_URL": "http://x/v1", "LLM_MODEL": "llama3"},
            "Local model llama3",
        ),
    ],
)
def test_describe_provider(env, text):
    assert describe_provider(env) == text


_ENV_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")
_OPENAI = "LLM_PROVIDER=openai\nLLM_API_KEY=sk-course\nLLM_BASE_URL=\nLLM_MODEL=gpt-4o\n"


@pytest.fixture
def clean_env(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _save_for_every_course() -> None:
    saved_provider.save_provider(
        {"LLM_PROVIDER": "anthropic", "LLM_API_KEY": "sk-ant", "LLM_BASE_URL": "", "LLM_MODEL": "claude-sonnet-5"}
    )


def test_validate_and_save_saves_for_every_course_and_applies_it(tmp_path, monkeypatch, clean_env):
    monkeypatch.setattr("chalk.config.complete", lambda prompt, max_tokens=5: {"text": "OK"})
    env_path = tmp_path / ".env"
    env_path.write_text(_OPENAI + "OTHER=kept\n", encoding="utf-8")

    saved = validate_and_save_provider(env_path, ProviderSettings("anthropic", "sk-ant", "", "claude-sonnet-5"))

    assert saved is True
    assert saved_provider.read_saved_provider()["LLM_MODEL"] == "claude-sonnet-5"
    assert read_env(env_path) == {"OTHER": "kept"}  # the course's own lines would override it
    assert os.environ["LLM_PROVIDER"] == "anthropic"


def test_validate_and_save_falls_back_to_the_course_when_the_store_refuses(
    tmp_path, monkeypatch, clean_env, memory_keyring
):
    from keyring.errors import PasswordSetError

    def _refuse(*args):
        raise PasswordSetError("locked")

    monkeypatch.setattr(memory_keyring, "set_password", _refuse)
    monkeypatch.setattr("chalk.config.complete", lambda prompt, max_tokens=5: {"text": "OK"})
    env_path = tmp_path / ".env"

    saved = validate_and_save_provider(env_path, ProviderSettings("anthropic", "sk-ant", "", "claude-sonnet-5"))

    assert saved is False
    assert read_env(env_path)["LLM_API_KEY"] == "sk-ant"


def test_a_course_without_its_own_provider_uses_the_saved_one(tmp_path):
    env_path = tmp_path / ".env"
    assert not env_is_configured(env_path)

    _save_for_every_course()

    assert env_is_configured(env_path)
    assert effective_env(env_path)["LLM_API_KEY"] == "sk-ant"


def test_a_course_with_a_complete_provider_of_its_own_keeps_it(tmp_path):
    _save_for_every_course()
    env_path = tmp_path / ".env"
    env_path.write_text(_OPENAI, encoding="utf-8")
    assert effective_env(env_path)["LLM_API_KEY"] == "sk-course"

    env_path.write_text("LLM_MODEL=gpt-4o\n", encoding="utf-8")  # incomplete: not used
    assert effective_env(env_path)["LLM_API_KEY"] == "sk-ant"


def test_the_first_course_with_a_key_shares_it_with_every_course(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(_OPENAI, encoding="utf-8")

    assert adopt_project_provider(env_path) is True
    assert saved_provider.read_saved_provider()["LLM_API_KEY"] == "sk-course"
    assert adopt_project_provider(env_path) is False  # something is saved now


def test_adopting_never_replaces_a_saved_provider(tmp_path):
    _save_for_every_course()
    env_path = tmp_path / ".env"
    env_path.write_text(_OPENAI, encoding="utf-8")

    assert adopt_project_provider(env_path) is False
    assert saved_provider.read_saved_provider()["LLM_API_KEY"] == "sk-ant"


def test_applying_a_course_without_a_provider_clears_the_previous_ones(tmp_path, clean_env):
    first = tmp_path / "first.env"
    first.write_text(_OPENAI, encoding="utf-8")
    apply_provider_env(first)
    assert os.environ["LLM_API_KEY"] == "sk-course"

    apply_provider_env(tmp_path / "second.env")  # no .env, nothing saved

    assert "LLM_API_KEY" not in os.environ


def test_a_corrupt_saved_provider_reads_as_none(memory_keyring):
    memory_keyring.set_password(saved_provider.SERVICE, saved_provider.ENTRY, "{not json")
    assert saved_provider.read_saved_provider() == {}


def test_validate_and_save_writes_nothing_when_the_test_call_fails(tmp_path, monkeypatch):
    def _reject(prompt, max_tokens=5):
        raise LLMProviderError("The Anthropic API key was not accepted.")

    monkeypatch.setattr("chalk.config.complete", _reject)
    env_path = tmp_path / ".env"

    with pytest.raises(LLMProviderError):
        validate_and_save_provider(env_path, ProviderSettings("anthropic", "bad", "", "claude-sonnet-5"))
    assert not env_path.exists()
