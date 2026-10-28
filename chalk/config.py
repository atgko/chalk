"""Project configuration: the LLM provider (saved once for every course
in the OS credential store, chalk/saved_provider.py, or in a project's own
`.env`) and `config.json` (institution, calendar file path, cost rates,
output preferences).

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

from dotenv import dotenv_values, set_key, unset_key

from chalk.errors import ChalkError
from chalk.llm_client import complete
from chalk.project import RESOURCES_DIR
from chalk.saved_provider import CredentialStoreError, read_saved_provider, save_provider

_BUNDLED_CONFIG = (RESOURCES_DIR / "config.json").resolve()
_REQUIRED_ENV_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL")
_ALL_ENV_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")


def load_config(config_path: Path) -> dict[str, Any]:
    """Load a project's config.json.

    A project created before a provider was added (e.g. Gemini) has no
    cost_rates section for it; the bundled defaults fill that in, so the
    model dropdown and cost tracking work without editing old projects.
    Sections the project does have are never touched.
    """
    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)
    if config_path.resolve() == _BUNDLED_CONFIG:
        return config
    with _BUNDLED_CONFIG.open("r", encoding="utf-8") as f:
        bundled_rates = json.load(f).get("cost_rates", {})
    return {**config, "cost_rates": {**bundled_rates, **config.get("cost_rates", {})}}


def read_env(env_path: Path) -> dict[str, str]:
    """Read the current .env values for a project.

    Returns an empty dict if the file doesn't exist yet — a fresh project
    has no .env until first-run setup writes one, and that's the expected
    state, not an error.
    """
    if not env_path.exists():
        return {}
    return {key: value for key, value in dotenv_values(env_path).items() if value is not None}


def _is_complete(values: dict[str, str]) -> bool:
    return all(values.get(key) for key in _REQUIRED_ENV_KEYS)


def effective_env(env_path: Path) -> dict[str, str]:
    """The provider a project uses: its own `.env` when that has a
    complete configuration, else the one saved for every course on this
    computer, else {}."""
    project = read_env(env_path)
    if _is_complete(project):
        return {key: project.get(key, "") for key in _ALL_ENV_KEYS}
    return read_saved_provider()


def env_is_configured(env_path: Path) -> bool:
    """Structural check only: does the project have a provider, its own
    or the computer's?

    This does NOT confirm the credentials actually work — that's
    validate_provider()'s job via a live test call. Used to decide
    whether to show first-run setup at all (PRD section 7.1: "Detect
    missing .env").
    """
    return _is_complete(effective_env(env_path))


def apply_provider_env(env_path: Path, *, override: bool = True) -> None:
    """Make the project's provider (effective_env) the live process
    configuration. A key that isn't configured is removed, so a course
    opened after another never borrows the first one's settings.

    With override=False (the CLI), each variable already set in the shell
    wins, and the project's `.env` fills the rest, over the saved
    provider, one variable at a time, as load_dotenv(override=False) did."""
    if not override:
        values = {**read_saved_provider(), **read_env(env_path)}
        for key in _ALL_ENV_KEYS:
            if values.get(key) and key not in os.environ:
                os.environ[key] = values[key]
        return
    values = effective_env(env_path)
    for key in _ALL_ENV_KEYS:
        if values.get(key):
            os.environ[key] = values[key]
        else:
            os.environ.pop(key, None)


def adopt_project_provider(env_path: Path) -> bool:
    """Courses created before the key was saved computer-wide keep it in
    their `.env`. The first such course opened shares it with every
    course, if nothing is saved yet. Returns True when it did."""
    project = read_env(env_path)
    if not _is_complete(project) or _is_complete(read_saved_provider()):
        return False
    try:
        save_provider(project)
    except CredentialStoreError:
        return False
    return True


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

PROVIDER_CHOICES = ("OpenAI", "Anthropic Claude", "Google Gemini", "Local model (Ollama)")
OPENAI_BASE_URL = "https://api.openai.com/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_OLLAMA_URL = "http://localhost:11434/v1"
DEFAULT_OLLAMA_MODEL = "llama3.1:70b"

COST_RATE_SECTION = {"OpenAI": "openai", "Anthropic Claude": "anthropic", "Google Gemini": "gemini"}
_FOOTER_LABEL = {
    "OpenAI": "OpenAI",
    "Anthropic Claude": "Anthropic",
    "Google Gemini": "Gemini",
    "Local model (Ollama)": "Local model",
}


@dataclass(frozen=True)
class ProviderSettings:
    """What the provider form produces, checked and ready to write to .env."""
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
    if choice not in COST_RATE_SECTION:
        raise ValueError(f"Unknown provider choice: {choice!r}")
    if not api_key:
        raise ChalkError(f"Paste your {choice} API key to continue.")
    if not model:
        raise ChalkError("Choose a model to continue.")
    if choice == "OpenAI":
        return ProviderSettings("openai", api_key, OPENAI_BASE_URL, model)
    if choice == "Google Gemini":
        return ProviderSettings("gemini", api_key, GEMINI_BASE_URL, model)
    return ProviderSettings("anthropic", api_key, "", model)


def choice_for_env(env: dict[str, str]) -> str:
    """Which PROVIDER_CHOICES entry an existing .env corresponds to."""
    provider = env.get("LLM_PROVIDER", "").lower()
    if provider == "anthropic":
        return "Anthropic Claude"
    if provider == "gemini":
        return "Google Gemini"
    base_url = env.get("LLM_BASE_URL", "")
    if base_url and "api.openai.com" not in base_url:
        return "Local model (Ollama)"
    return "OpenAI"


def model_options(config: dict[str, Any], choice: str) -> list[str]:
    """Model dropdown choices: the cost_rates keys for a hosted provider, so
    every selectable model has a cost rate (DECISIONS.md), with the
    recommended one first so a new setup starts on it. Empty for Ollama,
    whose model name stays free text."""
    section = COST_RATE_SECTION.get(choice)
    if section is None:
        return []
    return sorted(config.get("cost_rates", {}).get(section, {}), key=lambda model: model not in RECOMMENDED_MODELS)


# The best value for each hosted provider (UAT round 2: staff may not know
# which model to pick). The other models are labelled by what they cost
# next to it (`model_label`).
RECOMMENDED_MODELS = frozenset({"gpt-4o-mini", "claude-haiku-4-5-20251001", "gemini-3.5-flash-lite"})


def model_label(config: dict[str, Any], choice: str, model: str) -> str:
    """The model dropdown's text: the recommended model says so, and a
    pricier one says it's for heavier work and roughly what it costs next
    to the recommended one, e.g. "gpt-4o (Most capable, for long syllabi
    and heavier work: about 17× the cost)"."""
    if model in RECOMMENDED_MODELS:
        return f"{model} (Recommended: best value for everyday work)"
    rates = config.get("cost_rates", {}).get(COST_RATE_SECTION.get(choice, ""), {})
    recommended = next((rates[name] for name in rates if name in RECOMMENDED_MODELS), None)
    if model not in rates or not recommended or not recommended.get("output_per_1k"):
        return model
    ratio = round(rates[model]["output_per_1k"] / recommended["output_per_1k"])
    cost = f"about {ratio}× the cost" if ratio > 1 else "about the same cost"
    return f"{model} (Most capable, for long syllabi and heavier work: {cost})"


def describe_provider(env: dict[str, str]) -> str:
    """Footer text, e.g. "OpenAI gpt-4o" (PRD section 7.1)."""
    if not all(env.get(key) for key in _REQUIRED_ENV_KEYS):
        return "Not configured"
    return f"{_FOOTER_LABEL[choice_for_env(env)]} {env['LLM_MODEL']}"


def validate_and_save_provider(env_path: Path, settings: ProviderSettings) -> bool:
    """Test-call the candidate settings, and only if that succeeds save
    them for every course and make them the live process configuration.

    The project's own `.env` provider lines are removed, since they would
    otherwise override what was just saved. If the credential store
    refuses, the settings go in the project's `.env` instead. Returns True
    when they were saved for every course."""
    validate_provider(settings.provider, settings.api_key, settings.base_url, settings.model)
    values = {
        "LLM_PROVIDER": settings.provider,
        "LLM_API_KEY": settings.api_key,
        "LLM_BASE_URL": settings.base_url,
        "LLM_MODEL": settings.model,
    }
    try:
        save_provider(values)
    except CredentialStoreError:
        write_provider_env(
            env_path,
            provider=settings.provider,
            api_key=settings.api_key,
            base_url=settings.base_url,
            model=settings.model,
        )
        saved_for_every_course = False
    else:
        _remove_provider_lines(env_path)
        saved_for_every_course = True
    os.environ.update(values)
    return saved_for_every_course


def _remove_provider_lines(env_path: Path) -> None:
    for key in set(read_env(env_path)) & set(_ALL_ENV_KEYS):
        unset_key(str(env_path), key)
