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


def anthropic_response(text="hello", input_tokens=10, output_tokens=5, content=None):
    return SimpleNamespace(
        content=content if content is not None else [SimpleNamespace(type="text", text=text)],
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


def openai_out_of_credits_error():
    # The OpenAI SDK passes the inner "error" object as the body.
    body = {"message": "You exceeded your current quota.", "code": "insufficient_quota"}
    return openai.RateLimitError(
        "quota", response=httpx.Response(429, request=_request()), body=body
    )


def openai_status_error(error_cls, status, message):
    return error_cls(
        f"Error code: {status}",
        response=httpx.Response(status, request=_request()),
        body={"message": message},
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


def test_gemini_uses_the_openai_client_with_googles_url_and_low_reasoning(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "AIza-test")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.5-flash")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    instances = patch_openai(monkeypatch, [openai_response(text="quiz draft")])

    result = complete("Write a quiz.")

    assert result["text"] == "quiz draft"
    assert instances[0].init_kwargs["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/"
    call = instances[0].chat.completions.calls[0]
    assert call["model"] == "gemini-3.5-flash"
    assert call["reasoning_effort"] == "low"


def test_openai_requests_do_not_send_reasoning_effort(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    instances = patch_openai(monkeypatch, [openai_response()])

    complete("prompt")

    assert "reasoning_effort" not in instances[0].chat.completions.calls[0]


def test_missing_answer_text_becomes_an_empty_string(monkeypatch):
    # A thinking model can spend the whole token limit before answering.
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    patch_openai(monkeypatch, [openai_response(text=None)])

    assert complete("prompt")["text"] == ""


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


def test_anthropic_skips_thinking_blocks_and_joins_text_blocks(monkeypatch):
    # Models with adaptive thinking (e.g. claude-sonnet-5) may put a thinking
    # block, which has no .text, ahead of the answer.
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    content = [
        SimpleNamespace(type="thinking", thinking="", signature="sig"),
        SimpleNamespace(type="text", text="Question 1"),
        SimpleNamespace(type="text", text="\nQuestion 2"),
    ]
    patch_anthropic(monkeypatch, [anthropic_response(content=content)])

    result = complete("Write a quiz.")

    assert result["text"] == "Question 1\nQuestion 2"


# ---- Error-message contract (PRD section 7.3) ----------------------------


@pytest.mark.parametrize(
    "provider,patch_fn,error_fn,expected",
    [
        (
            "openai",
            patch_openai,
            openai_auth_error,
            "The OpenAI API key was not accepted. Check it at platform.openai.com and try again.",
        ),
        (
            "anthropic",
            patch_anthropic,
            anthropic_auth_error,
            "The Anthropic API key was not accepted. Check it at console.anthropic.com and try again.",
        ),
        (
            "gemini",
            patch_openai,
            openai_auth_error,
            "The Gemini API key was not accepted. Check it at aistudio.google.com and try again.",
        ),
    ],
)
def test_auth_error_becomes_the_prd_message_for_each_provider(
    monkeypatch, provider, patch_fn, error_fn, expected
):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    patch_fn(monkeypatch, [error_fn()])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert exc_info.value.user_message == expected


def test_auth_error_on_a_local_endpoint_names_the_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    patch_openai(monkeypatch, [openai_auth_error()])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert "http://localhost:11434/v1" in exc_info.value.user_message


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
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    patch_fn(monkeypatch, [error_fn()])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert exc_info.value.user_message == (
        "Could not reach the LLM provider. Check your connection. "
        "Extraction and rollover work without a connection."
    )


def test_connection_error_on_a_local_endpoint_uses_the_ollama_message(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "http://vm.example.edu:11434/v1")
    patch_openai(monkeypatch, [openai_connection_error()])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert exc_info.value.user_message == (
        "Could not reach the local model at http://vm.example.edu:11434/v1. Check that "
        "Ollama is running and the URL in your .env is correct."
    )


def test_unexpected_error_is_wrapped_with_the_exception_type_name(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    patch_openai(monkeypatch, [ValueError("boom")])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert exc_info.value.user_message == "Unexpected error from LLM provider: ValueError"


def test_permission_denied_explains_the_likely_causes_and_shows_the_provider_text(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    error = openai_status_error(
        openai.PermissionDeniedError, 403, "Country, region, or territory not supported"
    )
    patch_openai(monkeypatch, [error])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    message = exc_info.value.user_message
    assert message.startswith("OpenAI refused this request (error 403).")
    assert '"gpt-4o"' in message
    assert message.endswith("Provider said: Country, region, or territory not supported")


def test_anthropic_status_error_reads_the_nested_provider_message(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    body = {"type": "error", "error": {"type": "permission_error", "message": "Key lacks access"}}
    error = anthropic.PermissionDeniedError(
        "Error code: 403",
        response=httpx.Response(403, request=_request("https://api.anthropic.com/v1/messages")),
        body=body,
    )
    patch_anthropic(monkeypatch, [error])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert exc_info.value.user_message.startswith("Anthropic refused this request (error 403).")
    assert exc_info.value.user_message.endswith("Provider said: Key lacks access")


def test_unknown_model_names_the_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-retired")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    patch_openai(monkeypatch, [openai_status_error(openai.NotFoundError, 404, "no such model")])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert exc_info.value.user_message.startswith(
        'The model "gpt-retired" isn\'t available to this OpenAI API key (error 404).'
    )


def test_other_status_errors_report_the_status_code(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    patch_openai(monkeypatch, [openai_status_error(openai.BadRequestError, 400, "bad param")])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert exc_info.value.user_message == (
        "OpenAI returned an error (status 400). Provider said: bad param"
    )


def test_provider_text_is_hidden_when_details_are_switched_off(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setattr("chalk.llm_client._SHOW_PROVIDER_DETAILS", False)
    patch_openai(monkeypatch, [openai_status_error(openai.BadRequestError, 400, "bad param")])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert exc_info.value.user_message == "OpenAI returned an error (status 400)."


# ---- Retry / backoff (DECISIONS.md) --------------------------------------


def test_out_of_credits_is_not_retried_and_says_to_add_credits(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setattr("chalk.llm_client.time.sleep", lambda seconds: None)
    instances = patch_openai(monkeypatch, [openai_out_of_credits_error(), openai_response()])

    with pytest.raises(LLMProviderError) as exc_info:
        complete("prompt")

    assert "no API credits" in exc_info.value.user_message
    assert "ChatGPT subscription does not include API use" in exc_info.value.user_message
    assert len(instances) == 1


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
