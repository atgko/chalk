"""Find a running Ollama server from the app, so an instructor doesn't
have to look up its address in a terminal (Nov 9 UAT).

Ollama listens on http://localhost:11434 unless the OLLAMA_HOST
environment variable says otherwise. Its native `/api/tags` endpoint
lists the models that have been pulled, which needs no key and answers
in well under a second, so Chalk can check each likely address and offer
the models it finds. Chalk talks to Ollama through its OpenAI-compatible
API, which lives under `/v1` on the same address.

Standard library only, and every network error is swallowed: detection
is a convenience, and the instructor can always type the address.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

DEFAULT_HOST = "http://localhost:11434"
_TAGS_PATH = "/api/tags"
_TIMEOUT_SECONDS = 1.5
_MAX_RESPONSE_BYTES = 1_000_000

FIND_ADDRESS_HELP = (
    "Ollama runs at `http://localhost:11434` unless it was set up differently. To check: open a "
    "terminal (Command Prompt on Windows) and run `ollama list`. If it lists your models, Ollama is "
    "running on this computer. If it says it can't connect, start the Ollama app (or run "
    "`ollama serve`) and click **Find Ollama** again. If Ollama runs on another computer or a "
    "university server, ask whoever set it up for its address and type it here, ending in "
    "`/v1`, e.g. `http://10.0.0.5:11434/v1`. A custom address on this computer is in the "
    "`OLLAMA_HOST` setting."
)


@dataclass(frozen=True)
class OllamaServer:
    """A running Ollama found at `base_url` (the OpenAI-compatible address
    Chalk saves, ending in /v1), with the models pulled on it."""

    base_url: str
    models: tuple[str, ...]


Fetch = Callable[[str, float], bytes]


def candidate_hosts(environ: dict[str, str] | None = None, typed_url: str = "") -> list[str]:
    """The addresses worth trying, most likely first, without repeats: the
    one the instructor typed, OLLAMA_HOST, then the defaults."""
    environ = os.environ if environ is None else environ
    hosts = [typed_url, environ.get("OLLAMA_HOST", ""), DEFAULT_HOST, "http://127.0.0.1:11434"]
    seen: list[str] = []
    for host in hosts:
        normalized = normalize_host(host)
        if normalized and normalized not in seen:
            seen.append(normalized)
    return seen


def normalize_host(text: str) -> str:
    """ "localhost:11434", "http://localhost:11434/v1/" or "0.0.0.0" ->
    "http://localhost:11434"-style scheme://host:port; "" for blank text.
    Ollama's bind-all address 0.0.0.0 is reached as localhost."""
    text = text.strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    parts = urlsplit(text)
    host = parts.hostname or ""
    if not host:
        return ""
    if host in ("0.0.0.0", "::"):
        host = "localhost"
    port = parts.port or 11434
    return urlunsplit((parts.scheme or "http", f"{host}:{port}", "", "", ""))


def openai_base_url(host: str) -> str:
    """The address Chalk saves for a host: its OpenAI-compatible /v1 API."""
    return normalize_host(host) + "/v1"


def find_ollama(hosts: Iterable[str], fetch: Fetch | None = None) -> OllamaServer | None:
    """The first host in `hosts` where Ollama answers, or None."""
    fetch = fetch or _fetch
    for host in hosts:
        models = _list_models(host, fetch)
        if models is not None:
            return OllamaServer(base_url=openai_base_url(host), models=models)
    return None


def _list_models(host: str, fetch: Fetch) -> tuple[str, ...] | None:
    """The pulled models' names, or None if nothing Ollama-like answered."""
    try:
        payload = json.loads(fetch(host + _TAGS_PATH, _TIMEOUT_SECONDS))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        return None
    names = (entry.get("name") or entry.get("model") for entry in payload["models"] if isinstance(entry, dict))
    return tuple(sorted(name for name in names if isinstance(name, str) and name))


def _fetch(url: str, timeout: float) -> bytes:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Not a web address: {url}")
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read(_MAX_RESPONSE_BYTES)

