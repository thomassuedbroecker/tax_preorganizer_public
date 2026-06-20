"""Server-side endpoint tests for the agent REST service."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
import time
from types import SimpleNamespace

import pytest

# The in-app agent service needs the optional [agent] extra (langgraph). Skip
# these tests cleanly when it is not installed (e.g. the minimal CI job).
pytest.importorskip("langgraph")

from invoice_sorter import agent_service


def test_agent_functions_use_per_feature_default_models(monkeypatch):
    models = []

    class FakeAgent:
        def invoke(self, _state):
            return {"messages": [SimpleNamespace(content="OK")]}

    def fake_create_agent(_prompt, _base_url, model, _temperature):
        models.append(model)
        return FakeAgent()

    monkeypatch.setattr(agent_service, "_create_agent", fake_create_agent)

    agent_service.run_document_advice({"file_name": "anonymous.pdf"})
    agent_service.run_executive_report({"processed": 1})
    agent_service.run_document_chat({"file_name": "anonymous.pdf"}, "Category?")

    assert models == [
        agent_service.DEFAULT_ADVICE_MODEL,
        agent_service.DEFAULT_REPORT_MODEL,
        agent_service.DEFAULT_CHAT_MODEL,
    ]


def test_clean_model_output_strips_think_and_extracts_json():
    from invoice_sorter.agent_service import _clean_model_output

    assert _clean_model_output("<think>reasoning here</think>Hello there") == "Hello there"
    blob = '{"file_name": "x.pdf", "tax_preparer_advice": "Please verify the vendor."}'
    assert _clean_model_output(blob) == "Please verify the vendor."
    assert _clean_model_output("Just plain prose.") == "Just plain prose."


def start_handle():
    handle = agent_service.start_agent_server(host="127.0.0.1", port=0)
    # wait for server to be ready
    time.sleep(0.1)
    return handle


def test_executive_report_stream_endpoint(monkeypatch):
    # mock the internal report generator
    def fake_run_executive_report(summary, base_url=None, model=None, temperature=0.2):
        return "This is a streamed report. " * 5

    monkeypatch.setattr(agent_service, "run_executive_report", fake_run_executive_report)

    handle = start_handle()
    try:
        port = handle.server.server_address[1]
        url = f"http://127.0.0.1:{port}/api/executive-report-stream"
        payload = json.dumps({"summary": {"processed": 1}}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            chunks = []
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                obj = json.loads(line)
                chunks.append(obj.get("chunk", ""))
        assert "This is a streamed report." in "".join(chunks)
    finally:
        handle.shutdown()


def test_document_chat_endpoint(monkeypatch):
    captured = {}

    def fake_run_document_chat(document, message, history=None, base_url=None,
                               model=None, temperature=0.2, categories=None):
        captured["message"] = message
        captured["categories"] = categories
        return "You could file this under Internet."

    monkeypatch.setattr(agent_service, "run_document_chat", fake_run_document_chat)

    handle = start_handle()
    try:
        port = handle.server.server_address[1]
        url = f"http://127.0.0.1:{port}/api/document-chat"
        body = {"document": {"file_name": "a.pdf"}, "message": "Which category?",
                "categories": ["Internet", "Sonstiges"]}
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        assert data.get("reply") == "You could file this under Internet."
        assert captured["message"] == "Which category?"
        assert captured["categories"] == ["Internet", "Sonstiges"]
    finally:
        handle.shutdown()


def test_document_chat_endpoint_requires_message(monkeypatch):
    handle = start_handle()
    try:
        port = handle.server.server_address[1]
        url = f"http://127.0.0.1:{port}/api/document-chat"
        payload = json.dumps({"document": {"file_name": "a.pdf"}}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "expected HTTP 500"
        except urllib.error.HTTPError as exc:
            assert exc.code == 500
    finally:
        handle.shutdown()


def test_document_advice_endpoint(monkeypatch):
    def fake_run_document_advice(document, base_url=None, model=None, temperature=0.2):
        return "Advice for document"

    monkeypatch.setattr(agent_service, "run_document_advice", fake_run_document_advice)

    handle = start_handle()
    try:
        port = handle.server.server_address[1]
        url = f"http://127.0.0.1:{port}/api/document-advice"
        payload = json.dumps({"document": {"file_name": "a.pdf"}}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        assert data.get("advice") == "Advice for document"
    finally:
        handle.shutdown()
