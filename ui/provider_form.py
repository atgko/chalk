"""LLM provider form, shared by first-run setup and the Settings tab
(DECISIONS.md: Settings reuses the first-run form)."""

from __future__ import annotations

import streamlit as st

from chalk.config import (
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    PROVIDER_CHOICES,
    choice_for_env,
    load_config,
    model_options,
    provider_settings,
    read_env,
    validate_and_save_provider,
)
from chalk.errors import ChalkError
from chalk.project import ProjectPaths

_LOCAL = "Local model (Ollama)"
_CAPTIONS = (
    "Paste an API key from platform.openai.com",
    "Paste an API key from console.anthropic.com",
    "Enter your endpoint URL (e.g. http://localhost:11434/v1) and model name",
)


def render(paths: ProjectPaths, *, submit_label: str, key: str) -> bool:
    """Draw the form; returns True on the run where settings were
    validated with a test call and saved."""
    env = read_env(paths.env)
    saved_choice = choice_for_env(env) if env else "OpenAI"
    choice = st.radio(
        "LLM provider",
        PROVIDER_CHOICES,
        index=PROVIDER_CHOICES.index(saved_choice),
        captions=_CAPTIONS,
        key=f"{key}-choice",
    )
    is_saved_choice = bool(env) and choice == saved_choice

    if choice == _LOCAL:
        base_url = st.text_input(
            "Endpoint URL",
            value=env.get("LLM_BASE_URL", "") if is_saved_choice else DEFAULT_OLLAMA_URL,
            key=f"{key}-url",
        )
        model = st.text_input(
            "Model name",
            value=env.get("LLM_MODEL", "") if is_saved_choice else DEFAULT_OLLAMA_MODEL,
            key=f"{key}-local-model",
        )
        api_key = env.get("LLM_API_KEY", "") if is_saved_choice else ""
    else:
        base_url = ""
        has_saved_key = is_saved_choice and bool(env.get("LLM_API_KEY"))
        api_key = st.text_input(
            "API key",
            type="password",
            placeholder="Leave blank to keep the saved key" if has_saved_key else "",
            key=f"{key}-api-key-{choice}",
        ) or (env.get("LLM_API_KEY", "") if has_saved_key else "")
        options = model_options(load_config(paths.config_json), choice)
        saved_model = env.get("LLM_MODEL")
        model = st.selectbox(
            "Model",
            options,
            index=options.index(saved_model) if is_saved_choice and saved_model in options else 0,
            key=f"{key}-model-{choice}",
        )

    if not st.button(submit_label, type="primary", key=f"{key}-submit"):
        return False
    try:
        settings = provider_settings(choice, api_key=api_key, model=model or "", base_url=base_url)
        with st.spinner("Testing the connection…"):
            validate_and_save_provider(paths.env, settings)
    except ChalkError as exc:
        st.error(exc.user_message)
        return False
    return True
