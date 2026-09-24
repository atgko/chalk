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
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, set_key

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
