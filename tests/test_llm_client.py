"""Tests for chalk.llm_client — the only module allowed to import openai
or anthropic directly. We fake both SDKs' client classes rather than
hitting a real API: this exercises provider routing, the PRD section
7.3 error-message contract, and the DECISIONS.md retry/backoff behavior,
all without a network call.
"""

from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import openai
import pytest

from chalk.errors import LLMProviderError
from chalk.llm_client import complete

# ---- Fakes ------------------------------------------------------------


class ScriptedEndpoint:
    """Fake `.chat.completions` (OpenAI) / `.messages` (Anthropic) object.

    `.create()` pops the next scripted outcome from a shared queue — an
    exception to raise, or a response object to return. The queue is
    shared by reference (never copied), because chalk.llm_client builds a
    fresh client on every retry attempt; each new client's endpoint must
    pick up where the last one left off.
    """

    def __init__(self, outcomes):
        self._outcomes = outcomes
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeOpenAIClient:
    def __init__(self, outcomes, instances, **init_kwargs):
        self.init_kwargs = init_kwargs
        self.chat = SimpleNamespace(completions=ScriptedEndpoint(outcomes))
        instances.append(self)


class FakeAnthropicClient:
    def __init__(self, outcomes, instances, **init_kwargs):
        self.init_kwargs = init_kwargs
        self.messages = ScriptedEndpoint(outcomes)
        instances.append(self)


def patch_openai(monkeypatch, outcomes):
    instances: list[FakeOpenAIClient] = []
    monkeypatch.setattr(
        openai, "OpenAI", lambda **kwargs: FakeOpenAIClient(outcomes, instances, **kwargs)
    )
    return instances


def patch_anthropic(monkeypatch, outcomes):
    instances: list[FakeAnthropicClient] = []
    monkeypatch.setattr(
        anthropic,
        "Anthropic",
        lambda **kwargs: FakeAnthropicClient(outcomes, instances, **kwargs),
    )
    return instances


def openai_response(text="hello", input_tokens=10, output_tokens=5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=input_tokens, completion_tokens=output_tokens),
    )


def anthropic_response(text="hello", input_tokens=10, output_tokens=5):
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _request(url="https://api.example.com/v1/chat/completions"):
    return httpx.Request("POST", url)


def openai_auth_error():
    return openai.AuthenticationError(
        "invalid api key", response=httpx.Response(401, request=_request()), body=None
    )


def openai_rate_limit_error():
    return openai.RateLimitError(
        "rate limited", response=httpx.Response(429, request=_request()), body=None
    )


def openai_connection_error():
    return openai.APIConnectionError(request=_request())


def anthropic_auth_error():
    return anthropic.AuthenticationError(
        "invalid api key",
        response=httpx.Response(401, request=_request("https://api.anthropic.com/v1/messages")),
        body=None,
    )


def anthropic_connection_error():
    return anthropic.APIConnectionError(
        request=_request("https://api.anthropic.com/v1/messages")
    )


# ---- Provider routing ---------------------------------------------------


def test_openai_is_the_default_provider(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    instances = patch_openai(monkeypatch, [openai_response(text="quiz draft")])

    result = complete("Write a quiz.", system="You are a helper.")

    assert result == {"text": "quiz draft", "input_tokens": 10, "output_tokens": 5}
    assert instances[0].init_kwargs["api_key"] == "sk-test"


def test_openai_call_uses_configured_model_system_and_max_tokens(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    instances = patch_openai(monkeypatch, [openai_response()])

    complete("prompt text", system="system text", max_tokens=500)

    call = instances[0].chat.completions.calls[0]
    assert call["model"] == "gpt-4o-mini"
    assert call["max_tokens"] == 500
    assert call["messages"] == [
        {"role": "system", "content": "system text"},
        {"role": "user", "content": "prompt text"},
    ]


def test_anthropic_provider_routes_to_the_anthropic_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-5")
    instances = patch_anthropic(monkeypatch, [anthropic_response(text="rubric draft")])

    result = complete("Write a rubric.", system="You are a helper.")

    assert result == {"text": "rubric draft", "input_tokens": 10, "output_tokens": 5}
    call = instances[0].messages.calls[0]
    assert call["model"] == "claude-sonnet-5"
    assert call["system"] == "You are a helper."
    assert call["messages"] == [{"role": "user", "content": "Write a rubric."}]


# ---- Error-message contract (PRD section 7.3) ----------------------------


@pytest.mark.parametrize(
    "provider,patch_fn,error_fn",
    [
        ("openai", patch_openai, openai_auth_error),
        ("anthropic", patch_anthropic, anthropic_auth_error),
    ],
)
def test_auth_error_becomes_the_plain_english_message(monkeypatch, provider, patch_fn, error_fn):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    patch_fn(monkeypatch, [error_fn()])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert exc_info.value.user_message == "API key was not accepted. Check your key and try again."


@pytest.mark.parametrize(
    "provider,patch_fn,error_fn",
    [
        ("openai", patch_openai, openai_connection_error),
        ("anthropic", patch_anthropic, anthropic_connection_error),
    ],
)
def test_connection_error_becomes_the_plain_english_message(
    monkeypatch, provider, patch_fn, error_fn
):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    patch_fn(monkeypatch, [error_fn()])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert "Could not reach the LLM provider" in exc_info.value.user_message
    assert "Extraction and rollover work without a connection" in exc_info.value.user_message


def test_unexpected_error_is_wrapped_with_the_exception_type_name(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    patch_openai(monkeypatch, [ValueError("boom")])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert exc_info.value.user_message == "Unexpected error from LLM provider: ValueError"


# ---- Retry / backoff (DECISIONS.md) --------------------------------------


def test_transient_error_is_retried_and_can_still_succeed(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setattr("chalk.llm_client.time.sleep", lambda seconds: None)
    outcomes = [openai_rate_limit_error(), openai_rate_limit_error(), openai_response(text="ok")]
    patch_openai(monkeypatch, outcomes)

    result = complete("prompt")

    assert result["text"] == "ok"


def test_transient_error_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setattr("chalk.llm_client.time.sleep", lambda seconds: None)
    outcomes = [openai_rate_limit_error(), openai_rate_limit_error(), openai_rate_limit_error()]
    patch_openai(monkeypatch, outcomes)

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert "temporarily unavailable" in exc_info.value.user_message
