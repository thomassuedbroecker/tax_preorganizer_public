"""Tests for streaming agent client behavior."""

from __future__ import annotations

import json
import urllib.request

import pytest

# agent_client imports agent_service, which needs the optional [agent] extra
# (langgraph). Skip cleanly when it is not installed (e.g. the minimal CI job).
pytest.importorskip("langgraph")

from invoice_sorter.agent_client import (
    AgentClientOptions,
    request_document_chat,
    request_executive_report_stream,
)
from invoice_sorter import agent_client


class MockResponse:
    def __init__(self, lines: list[bytes]):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._lines)

    def read(self):
        return b"".join(self._lines)


def test_request_executive_report_stream_reads_ndjson(monkeypatch):
    # prepare ndjson bytes lines as the server would send
    lines = [b'{"chunk":"Hello "}\n', b'{"chunk":"world"}\n']

    def fake_urlopen(request, timeout=None):
        return MockResponse(lines)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    summary = {"processed": 1}
    chunks = list(request_executive_report_stream(summary, options=AgentClientOptions()))
    assert "".join(chunks) == "Hello world"


def test_post_json_surfaces_server_error(monkeypatch):
    # A 500 from the server carries {"error": "..."} — the client must surface it,
    # not a bare "HTTP Error 500".
    import io
    import urllib.error

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            url="http://x/api/document-chat", code=500, msg="Internal Server Error",
            hdrs=None,
            fp=io.BytesIO(b'{"error": "Ollama model \'llama3.2\' not found"}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as exc:
        agent_client._post_json("http://x/api/document-chat", {"a": 1})
    assert "llama3.2" in str(exc.value)
    assert "HTTP Error 500" not in str(exc.value)


def test_request_document_chat_posts_and_returns_reply(monkeypatch):
    captured = {}

    def fake_post_json(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return {"reply": "File it under Internet."}

    monkeypatch.setattr(agent_client, "_post_json", fake_post_json)

    reply = request_document_chat(
        {"file_name": "a.pdf"}, "Which category?",
        history=[{"role": "user", "content": "hi"}],
        categories=["Internet", "Sonstiges"],
    )
    assert reply == "File it under Internet."
    assert captured["url"].endswith("/api/document-chat")
    assert captured["payload"]["message"] == "Which category?"
    assert captured["payload"]["categories"] == ["Internet", "Sonstiges"]
