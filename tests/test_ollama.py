"""Finding a running Ollama from the app (Nov 9 UAT): which addresses are
tried, and what a found server offers. No network: a fake fetch stands in
for Ollama's /api/tags endpoint."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from chalk.ollama import (
    DEFAULT_HOST,
    OllamaServer,
    candidate_hosts,
    find_ollama,
    normalize_host,
    openai_base_url,
)

TAGS = json.dumps({"models": [{"name": "llama3.1:8b"}, {"name": "gemma3:4b"}, {"model": "qwen3"}]}).encode()


def _fake_fetch(answers: dict[str, bytes]):
    calls = []

    def fetch(url: str, timeout: float) -> bytes:
        calls.append(url)
        if url in answers:
            return answers[url]
        raise ConnectionRefusedError(url)

    fetch.calls = calls
    return fetch


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("http://localhost:11434/v1", "http://localhost:11434"),
        ("localhost:11434", "http://localhost:11434"),
        ("http://10.0.0.5:11434/v1/", "http://10.0.0.5:11434"),
        ("0.0.0.0", "http://localhost:11434"),
        ("http://0.0.0.0:8080", "http://localhost:8080"),
        ("https://ollama.example.edu", "https://ollama.example.edu:11434"),
        ("  ", ""),
    ],
)
def test_normalize_host(text, expected):
    assert normalize_host(text) == expected


def test_openai_base_url_ends_in_v1():
    assert openai_base_url("localhost:11434") == "http://localhost:11434/v1"


def test_candidates_put_the_typed_address_and_ollama_host_first_without_repeats():
    hosts = candidate_hosts({"OLLAMA_HOST": "0.0.0.0:9999"}, typed_url="http://vm:11434/v1")

    assert hosts == ["http://vm:11434", "http://localhost:9999", DEFAULT_HOST, "http://127.0.0.1:11434"]


def test_candidates_without_settings_are_the_defaults():
    assert candidate_hosts({}, typed_url=DEFAULT_HOST + "/v1") == [DEFAULT_HOST, "http://127.0.0.1:11434"]


def test_find_ollama_returns_the_first_address_that_answers_with_its_models():
    fetch = _fake_fetch({"http://127.0.0.1:11434/api/tags": TAGS})

    server = find_ollama([DEFAULT_HOST, "http://127.0.0.1:11434"], fetch)

    assert server == OllamaServer("http://127.0.0.1:11434/v1", ("gemma3:4b", "llama3.1:8b", "qwen3"))
    assert fetch.calls == [DEFAULT_HOST + "/api/tags", "http://127.0.0.1:11434/api/tags"]


def test_find_ollama_is_none_when_nothing_answers():
    assert find_ollama([DEFAULT_HOST], _fake_fetch({})) is None


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"error": "nope"}'])
def test_something_else_on_the_port_is_not_ollama(body):
    assert find_ollama([DEFAULT_HOST], _fake_fetch({DEFAULT_HOST + "/api/tags": body})) is None


def test_ollama_with_no_models_pulled_is_still_found():
    server = find_ollama([DEFAULT_HOST], _fake_fetch({DEFAULT_HOST + "/api/tags": b'{"models": []}'}))

    assert server == OllamaServer(DEFAULT_HOST + "/v1", ())


def test_find_ollama_talks_to_a_real_http_server():
    class Tags(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == "/api/tags" else 404)
            self.end_headers()
            self.wfile.write(TAGS)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Tags)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host = f"http://127.0.0.1:{server.server_port}"
        found = find_ollama([host])
    finally:
        server.shutdown()

    assert found is not None and found.models == ("gemma3:4b", "llama3.1:8b", "qwen3")
    assert found.base_url == host + "/v1"
