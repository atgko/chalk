"""Project configuration: `.env` (LLM provider credentials) and
`config.json` (institution, calendar file path, cost rates, output
preferences).

This is the one place that knows how to read/write a provider
configuration and validate it with a live test call — both the CLI's
first-run setup (PRD section 6.6) and the Streamlit Settings tab
(DECISIONS.md, which reuses the first-run form) call into this module
rather than duplicating the logic.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, set_key

from chalk.errors import ChalkError
from chalk.llm_client import complete

_REQUIRED_ENV_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL")
_ALL_ENV_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")


def load_config(config_path: Path) -> dict[str, Any]:
    """Load a project's config.json."""
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_env(env_path: Path) -> dict[str, str]:
    """Read the current .env values for a project.

    Returns an empty dict if the file doesn't exist yet — a fresh project
    has no .env until first-run setup writes one, and that's the expected
    state, not an error.
    """
    if not env_path.exists():
        return {}
    return {key: value for key, value in dotenv_values(env_path).items() if value is not None}


def env_is_configured(env_path: Path) -> bool:
    """Structural check only: are the required keys present and non-empty?

    This does NOT confirm the credentials actually work — that's
    validate_provider()'s job via a live test call. Used to decide
    whether to show first-run setup at all (PRD section 7.1: "Detect
    missing .env").
    """
    values = read_env(env_path)
    return all(values.get(key) for key in _REQUIRED_ENV_KEYS)


def write_provider_env(
    env_path: Path,
    *,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
) -> None:
    """Write the four provider variables to .env, creating the file (and
    its parent directory) if needed.

    This is the only function that writes .env — used by first-run setup
    and by the Settings tab alike, so there is exactly one code path that
    can put a provider configuration on disk.
    """
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if not env_path.exists():
        env_path.touch()
    set_key(str(env_path), "LLM_PROVIDER", provider)
    set_key(str(env_path), "LLM_API_KEY", api_key)
    set_key(str(env_path), "LLM_BASE_URL", base_url)
    set_key(str(env_path), "LLM_MODEL", model)


def validate_provider(provider: str, api_key: str, base_url: str, model: str) -> None:
    """Make a minimal test call to confirm a candidate provider
    configuration actually works, per PRD section 7.1 ("Key or URL
    validated with a test call before proceeding").

    Raises LLMProviderError (propagated from chalk.llm_client.complete)
    with a plain-English message on failure — the caller shows it
    directly and does not proceed to write .env. The candidate config is
    applied to the environment only for the duration of this call and the
    previous environment is always restored, success or failure, so a
    failed validation attempt never contaminates the process's actual
    provider config.
    """
    candidate = {
        "LLM_PROVIDER": provider,
        "LLM_API_KEY": api_key,
        "LLM_BASE_URL": base_url,
        "LLM_MODEL": model,
    }
    previous = {key: os.environ.get(key) for key in _ALL_ENV_KEYS}
    try:
        os.environ.update(candidate)
        complete("Reply with the single word OK.", max_tokens=5)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# ---- Provider form (first-run setup + Settings tab) --------------------------

PROVIDER_CHOICES = ("OpenAI", "Anthropic Claude", "Local model (Ollama)")
OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OLLAMA_URL = "http://localhost:11434/v1"
DEFAULT_OLLAMA_MODEL = "llama3.1:70b"

_COST_RATE_SECTION = {"OpenAI": "openai", "Anthropic Claude": "anthropic"}
_FOOTER_LABEL = {"OpenAI": "OpenAI", "Anthropic Claude": "Anthropic", "Local model (Ollama)": "Local model"}


@dataclass(frozen=True)
class ProviderSettings:
    provider: str
    api_key: str
    base_url: str
    model: str


def provider_settings(
    choice: str, *, api_key: str = "", model: str = "", base_url: str = ""
) -> ProviderSettings:
    """Turn the setup form's inputs into the four .env values (PRD
    section 11's three provider configurations). Raises ChalkError with a
    plain-English message for a missing required field."""
    api_key, model, base_url = api_key.strip(), model.strip(), base_url.strip()
    if choice == "Local model (Ollama)":
        return ProviderSettings(
            provider="openai",
            api_key=api_key or "ollama",
            base_url=base_url or DEFAULT_OLLAMA_URL,
            model=model or DEFAULT_OLLAMA_MODEL,
        )
    if choice not in _COST_RATE_SECTION:
        raise ValueError(f"Unknown provider choice: {choice!r}")
    if not api_key:
        raise ChalkError(f"Paste your {choice} API key to continue.")
    if not model:
        raise ChalkError("Choose a model to continue.")
    if choice == "OpenAI":
        return ProviderSettings("openai", api_key, OPENAI_BASE_URL, model)
    return ProviderSettings("anthropic", api_key, "", model)


def choice_for_env(env: dict[str, str]) -> str:
    """Which PROVIDER_CHOICES entry an existing .env corresponds to."""
    if env.get("LLM_PROVIDER", "").lower() == "anthropic":
        return "Anthropic Claude"
    base_url = env.get("LLM_BASE_URL", "")
    if base_url and "api.openai.com" not in base_url:
        return "Local model (Ollama)"
    return "OpenAI"


def model_options(config: dict[str, Any], choice: str) -> list[str]:
    """Model dropdown choices: the cost_rates keys for OpenAI/Anthropic, so
    every selectable model has a cost rate (DECISIONS.md). Empty for
    Ollama, whose model name stays free text."""
    section = _COST_RATE_SECTION.get(choice)
    if section is None:
        return []
    return list(config.get("cost_rates", {}).get(section, {}))


def describe_provider(env: dict[str, str]) -> str:
    """Footer text, e.g. "OpenAI gpt-4o" (PRD section 7.1)."""
    if not all(env.get(key) for key in _REQUIRED_ENV_KEYS):
        return "Not configured"
    return f"{_FOOTER_LABEL[choice_for_env(env)]} {env['LLM_MODEL']}"


def validate_and_save_provider(env_path: Path, settings: ProviderSettings) -> None:
    """Test-call the candidate settings, and only if that succeeds write
    them to .env and make them the live process configuration."""
    validate_provider(settings.provider, settings.api_key, settings.base_url, settings.model)
    write_provider_env(
        env_path,
        provider=settings.provider,
        api_key=settings.api_key,
        base_url=settings.base_url,
        model=settings.model,
    )
    os.environ.update(
        {
            "LLM_PROVIDER": settings.provider,
            "LLM_API_KEY": settings.api_key,
            "LLM_BASE_URL": settings.base_url,
            "LLM_MODEL": settings.model,
        }
    )
