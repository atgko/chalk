"""Provider-agnostic LLM client (PRD section 4.1).

This is the only module in Chalk that imports `openai` or `anthropic`
directly. Every other module calls `complete()` and never touches a
provider SDK — swapping providers is a `.env` change only
(`LLM_PROVIDER`/`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`), never a code
change. OpenAI and Ollama share one code path because Ollama exposes an
OpenAI-compatible API; Anthropic has a different response shape and is
handled in its own branch.

DECISIONS.md adds retry-with-backoff on top of the PRD's original sketch:
a transient rate-limit or timeout shouldn't force the instructor to
manually click Regenerate.
"""

from __future__ import annotations

import os
import time
from typing import Any, TypedDict

import anthropic
import openai

from chalk.errors import LLMProviderError

# A brief network blip gets a few short retries before we give up and
# surface LLMProviderError. Kept as small module constants rather than a
# config.json value — this is an internal reliability detail, not
# something instructors are expected to tune (YAGNI).
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0

_AUTH_EXCEPTIONS: tuple[type[Exception], ...] = (
    openai.AuthenticationError,
    anthropic.AuthenticationError,
)
_CONNECTION_EXCEPTIONS: tuple[type[Exception], ...] = (
    openai.APIConnectionError,
    anthropic.APIConnectionError,
)
_TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.APITimeoutError,
)


class CompletionResult(TypedDict):
    text: str
    input_tokens: int
    output_tokens: int


def _get_provider() -> str:
    return os.getenv("LLM_PROVIDER", "openai").lower()


def _call_openai(prompt: str, system: str, max_tokens: int) -> CompletionResult:
    client = openai.OpenAI(
        api_key=os.getenv("LLM_API_KEY", "ollama"),
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
    )
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "gpt-4o"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
    )
    return {
        "text": response.choices[0].message.content,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }


def _call_anthropic(prompt: str, system: str, max_tokens: int) -> CompletionResult:
    client = anthropic.Anthropic(api_key=os.getenv("LLM_API_KEY"))
    response = client.messages.create(
        model=os.getenv("LLM_MODEL", "claude-sonnet-5"),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return {
        "text": response.content[0].text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def complete(prompt: str, system: str = "", max_tokens: int = 2000) -> CompletionResult:
    """Send a prompt to the configured LLM provider.

    Returns {"text": str, "input_tokens": int, "output_tokens": int}.
    Raises LLMProviderError with a plain-English message on failure — the
    only exception type that escapes this module. Every caller wraps this
    call in a try/except for LLMProviderError and surfaces `.user_message`
    directly; no other exception from a provider SDK should reach
    user-facing code.
    """
    provider = _get_provider()
    call = _call_anthropic if provider == "anthropic" else _call_openai

    last_transient_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return call(prompt, system, max_tokens)

        except _AUTH_EXCEPTIONS as exc:
            raise LLMProviderError(
                "API key was not accepted. Check your key and try again."
            ) from exc

        except _CONNECTION_EXCEPTIONS as exc:
            raise LLMProviderError(
                "Could not reach the LLM provider. "
                "Check your internet connection. "
                "Extraction and rollover work without a connection."
            ) from exc

        except _TRANSIENT_EXCEPTIONS as exc:
            last_transient_error = exc
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))
                continue

        except Exception as exc:
            raise LLMProviderError(
                f"Unexpected error from LLM provider: {type(exc).__name__}"
            ) from exc

    raise LLMProviderError(
        "The LLM provider is temporarily unavailable after several attempts. "
        "Please try again in a moment."
    ) from last_transient_error
