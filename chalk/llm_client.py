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
from typing import TypedDict

import anthropic
import openai

from chalk.errors import LLMProviderError

# A brief network blip gets a few short retries before we give up and
# surface LLMProviderError. Kept as small module constants rather than a
# config.json value — this is an internal reliability detail, not
# something instructors are expected to tune (YAGNI).
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0

# TEMPORARY, for testing (BACKLOG.md): append the provider's own error text
# to refused-request messages so teammates can tell a restricted key from a
# blocked model or region. Set to False before the presentation.
_SHOW_PROVIDER_DETAILS = True

# OpenAI answers an account with no API credits with a 429 carrying this
# code. Retrying can't help, so it isn't treated as a transient rate limit.
_OUT_OF_CREDITS_CODE = "insufficient_quota"

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
_STATUS_EXCEPTIONS: tuple[type[Exception], ...] = (
    openai.APIStatusError,
    anthropic.APIStatusError,
)
_PERMISSION_EXCEPTIONS: tuple[type[Exception], ...] = (
    openai.PermissionDeniedError,
    anthropic.PermissionDeniedError,
)
_NOT_FOUND_EXCEPTIONS: tuple[type[Exception], ...] = (
    openai.NotFoundError,
    anthropic.NotFoundError,
)


class CompletionResult(TypedDict):
    text: str
    input_tokens: int
    output_tokens: int


_OPENAI_BASE_URL = "https://api.openai.com/v1"


def _get_provider() -> str:
    return os.getenv("LLM_PROVIDER", "openai").lower()


def _local_base_url() -> str | None:
    """The configured endpoint if it's a local/self-hosted OpenAI-compatible
    server (e.g. Ollama) rather than OpenAI itself, else None."""
    base_url = os.getenv("LLM_BASE_URL", "")
    if _get_provider() == "openai" and base_url and "api.openai.com" not in base_url:
        return base_url
    return None


def _auth_error_message() -> str:
    """PRD section 7.3's per-provider "key invalid" messages."""
    local_url = _local_base_url()
    if local_url:
        return f"The endpoint at {local_url} did not accept the API key. Check LLM_API_KEY in your .env."
    if _get_provider() == "anthropic":
        return "The Anthropic API key was not accepted. Check it at console.anthropic.com and try again."
    return "The OpenAI API key was not accepted. Check it at platform.openai.com and try again."


def _connection_error_message() -> str:
    local_url = _local_base_url()
    if local_url:
        return (
            f"Could not reach the local model at {local_url}. Check that Ollama is "
            "running and the URL in your .env is correct."
        )
    return (
        "Could not reach the LLM provider. Check your connection. "
        "Extraction and rollover work without a connection."
    )


def _provider_label() -> str:
    if _local_base_url():
        return "local model"
    return "Anthropic" if _get_provider() == "anthropic" else "OpenAI"


def _is_out_of_credits(exc: Exception) -> bool:
    return getattr(exc, "code", None) == _OUT_OF_CREDITS_CODE


def _out_of_credits_message() -> str:
    return (
        "Your OpenAI account has no API credits. Add credits at "
        "platform.openai.com/settings/organization/billing and try again. "
        "A ChatGPT subscription does not include API use."
    )


def _provider_detail(exc: Exception) -> str:
    """The provider's own explanation, from the error body when there is one.
    OpenAI's SDK passes the inner error object as the body; Anthropic's
    passes the whole response, with the message under "error"."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
    return str(getattr(exc, "message", "") or exc)


def _status_error_message(exc: Exception) -> str:
    """Messages for a request the provider received and refused (403, 404,
    and any other HTTP error without its own message)."""
    label = _provider_label()
    model = os.getenv("LLM_MODEL", "")
    if isinstance(exc, _PERMISSION_EXCEPTIONS):
        message = (
            f"{label} refused this request (error 403). The API key may be restricted, "
            f'the project may not allow the model "{model}", or the service may not be '
            "available in your region or network."
        )
    elif isinstance(exc, _NOT_FOUND_EXCEPTIONS):
        message = (
            f'The model "{model}" isn\'t available to this {label} API key (error 404). '
            "Choose a different model in Settings."
        )
    else:
        status = getattr(exc, "status_code", "unknown")
        message = f"{label} returned an error (status {status})."
    if _SHOW_PROVIDER_DETAILS:
        message += f" Provider said: {_provider_detail(exc)}"
    return message


def _call_openai(prompt: str, system: str, max_tokens: int) -> CompletionResult:
    client = openai.OpenAI(
        api_key=os.getenv("LLM_API_KEY", "ollama"),
        base_url=os.getenv("LLM_BASE_URL") or _OPENAI_BASE_URL,
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
    # Models with adaptive thinking may return thinking blocks (no .text)
    # ahead of the answer, so keep only the text blocks.
    return {
        "text": "".join(block.text for block in response.content if block.type == "text"),
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
            raise LLMProviderError(_auth_error_message()) from exc

        except _CONNECTION_EXCEPTIONS as exc:
            raise LLMProviderError(_connection_error_message()) from exc

        except _TRANSIENT_EXCEPTIONS as exc:
            if _is_out_of_credits(exc):
                raise LLMProviderError(_out_of_credits_message()) from exc
            last_transient_error = exc
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))
                continue

        except _STATUS_EXCEPTIONS as exc:
            raise LLMProviderError(_status_error_message(exc)) from exc

        except Exception as exc:
            raise LLMProviderError(
                f"Unexpected error from LLM provider: {type(exc).__name__}"
            ) from exc

    raise LLMProviderError(
        "The LLM provider is temporarily unavailable after several attempts. "
        "Please try again in a moment."
    ) from last_transient_error
