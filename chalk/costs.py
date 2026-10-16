"""USD cost from token counts and config.json's cost_rates (PRD section 11).

Rates are looked up per provider (PLAN.md Risk #10): a local/Ollama
endpoint always uses `cost_rates.local.default`, never a lookup of its
free-text model name; OpenAI and Anthropic use the rate for the exact
model. A hosted model with no rate in config.json yields None ("unknown"),
never a silent $0.
"""

from __future__ import annotations

from typing import Any

from chalk.config import choice_for_env

# DECISIONS.md estimate heuristic: ~4 characters per token.
CHARS_PER_TOKEN = 4

_SECTION_BY_CHOICE = {"OpenAI": "openai", "Anthropic Claude": "anthropic"}


def rate_for(config: dict[str, Any], env: dict[str, str]) -> dict[str, float] | None:
    rates = config.get("cost_rates", {})
    choice = choice_for_env(env)
    if choice == "Local model (Ollama)":
        return rates.get("local", {}).get("default", {"input_per_1k": 0.0, "output_per_1k": 0.0})
    return rates.get(_SECTION_BY_CHOICE[choice], {}).get(env.get("LLM_MODEL", ""))


def cost_usd(rate: dict[str, float] | None, input_tokens: int, output_tokens: int) -> float | None:
    if rate is None:
        return None
    return input_tokens / 1000 * rate["input_per_1k"] + output_tokens / 1000 * rate["output_per_1k"]


def estimate_tokens(text: str) -> int:
    """DECISIONS.md heuristic: characters / 4."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_max_cost(rate: dict[str, float] | None, prompt: str, max_tokens: int) -> float | None:
    """Upper-bound estimate shown before generation ("up to ~$X"): prompt
    tokens from its length, output assumed to hit the max_tokens ceiling."""
    return cost_usd(rate, estimate_tokens(prompt), max_tokens)


def format_cost(cost: float | None, *, prefix: str = "") -> str:
    """"$0.0123" (or "up to ~$0.0123"), or an explanation when unknown."""
    return "unknown (no cost rate for this model in config.json)" if cost is None else f"{prefix}${cost:.4f}"
