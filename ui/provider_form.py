"""LLM provider form, shared by first-run setup and the Settings tab
(DECISIONS.md: Settings reuses the first-run form)."""

from __future__ import annotations

import streamlit as st

from chalk.config import (
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    PROVIDER_CHOICES,
    choice_for_env,
    effective_env,
    load_config,
    model_label,
    model_options,
    provider_settings,
    validate_and_save_provider,
)
from chalk.errors import ChalkError
from chalk.ollama import FIND_ADDRESS_HELP, OllamaServer, candidate_hosts, find_ollama
from chalk.project import ProjectPaths

_LOCAL = "Local model (Ollama)"
def captions() -> tuple[str, ...]:
    """Each provider's one-line hint. The providers' sites are named, not
    linked: a link to a page that moves would break, and these aren't in
    the links file (Nov 10 UAT)."""
    return (
        "Paste an API key from your OpenAI account (platform.openai.com).",
        "Paste an API key from your Anthropic account (console.anthropic.com).",
        (
            "Paste an API key from your Google AI Studio account (aistudio.google.com). "
            "Not approved by the university for student data."
        ),
        # In backticks, so the address isn't a link: opening it in a browser
        # shows a "page not found" error (Nov 9 UAT).
        (
            "Runs on your own computer or a university server. Usually at `http://localhost:11434/v1`; "
            "click Find Ollama to check. Ollama itself is free from ollama.com."
        ),
    )


SAVED_EVERYWHERE = "Connected. Your key is saved on this computer for all your courses."
SAVED_HERE = (
    "Connected. This computer's password store wasn't available, so your key is saved for this "
    "course only."
)


def render(paths: ProjectPaths, *, submit_label: str, key: str) -> str | None:
    """Draw the form. On the run where settings were validated with a
    test call and saved, returns a message saying where they were saved;
    otherwise None."""
    env = effective_env(paths.env)
    saved_choice = choice_for_env(env) if env else "OpenAI"
    choice = st.radio(
        "LLM provider",
        PROVIDER_CHOICES,
        index=PROVIDER_CHOICES.index(saved_choice),
        captions=captions(),
        key=f"{key}-choice",
    )
    is_saved_choice = bool(env) and choice == saved_choice

    if choice == _LOCAL:
        base_url, model = _local_model_fields(env if is_saved_choice else {}, key)
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
        config = load_config(paths.config_json)
        options = model_options(config, choice)
        saved_model = env.get("LLM_MODEL")
        model = st.selectbox(
            "Model",
            options,
            index=options.index(saved_model) if is_saved_choice and saved_model in options else 0,
            format_func=lambda option: model_label(config, choice, option),
            key=f"{key}-model-{choice}",
            help="Not sure? The recommended model handles drafts and syllabi well for a fraction "
            "of the cost. Pick the most capable one for very long syllabi or harder content.",
        )

    if not st.button(submit_label, type="primary", key=f"{key}-submit"):
        return None
    try:
        settings = provider_settings(choice, api_key=api_key, model=model or "", base_url=base_url)
        with st.spinner("Testing the connection…"):
            saved_everywhere = validate_and_save_provider(paths.env, settings)
    except ChalkError as exc:
        st.error(exc.user_message)
        return None
    return SAVED_EVERYWHERE if saved_everywhere else SAVED_HERE


def _local_model_fields(saved_env: dict[str, str], key: str) -> tuple[str, str]:
    """Ollama's address and model, pre-filled with the saved values or the
    defaults from the README, plus a Find Ollama button that checks the
    likely addresses and lists the models pulled there (Nov 9 UAT)."""
    url_key, model_key, found_key = f"{key}-url", f"{key}-local-model", f"{key}-ollama-found"
    st.session_state.setdefault(url_key, saved_env.get("LLM_BASE_URL") or DEFAULT_OLLAMA_URL)
    st.session_state.setdefault(model_key, saved_env.get("LLM_MODEL") or DEFAULT_OLLAMA_MODEL)
    base_url = st.text_input("Endpoint URL", key=url_key, help=FIND_ADDRESS_HELP)
    st.button("Find Ollama", key=f"{key}-find", on_click=_find_ollama, args=(url_key, model_key, found_key))

    found: OllamaServer | None | bool = st.session_state.get(found_key, False)
    if found is None:
        st.warning("Couldn't find Ollama on this computer. " + FIND_ADDRESS_HELP)
    elif found and found.models:
        st.success(f"Found Ollama at `{found.base_url}` with {len(found.models)} model(s).")
        current = st.session_state[model_key]
        options = list(found.models) if current in found.models else [current, *found.models]
        return base_url, st.selectbox("Model name", options, key=model_key)
    elif found:
        st.warning(
            f"Found Ollama at `{found.base_url}`, but no models are installed yet. In a terminal, run "
            f"`ollama pull {DEFAULT_OLLAMA_MODEL}` (or a smaller model such as `llama3.1:8b`), then "
            "click Find Ollama again."
        )
    model = st.text_input("Model name", key=model_key, help="The name `ollama list` shows, e.g. `llama3.1:8b`.")
    return base_url, model


def _find_ollama(url_key: str, model_key: str, found_key: str) -> None:
    """Button callback, so the fields can still be changed before they're drawn."""
    found = find_ollama(candidate_hosts(typed_url=st.session_state.get(url_key, "")))
    st.session_state[found_key] = found
    if found is None:
        return
    st.session_state[url_key] = found.base_url
    if found.models and st.session_state.get(model_key) not in found.models:
        st.session_state[model_key] = found.models[0]
