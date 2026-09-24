import json
import os

import pytest

from chalk.config import (
    env_is_configured,
    load_config,
    read_env,
    validate_provider,
    write_provider_env,
)
from chalk.errors import LLMProviderError


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
