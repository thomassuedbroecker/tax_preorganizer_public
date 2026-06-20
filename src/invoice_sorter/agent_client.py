from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .agent_service import DEFAULT_AGENT_URL


@dataclass
class AgentClientOptions:
    base_url: str = DEFAULT_AGENT_URL
    model: str | None = None
    temperature: float = 0.2


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # The server returns {"error": "..."} on non-2xx; surface that message
        # instead of a bare "HTTP Error 500".
        detail = ""
        try:
            body = exc.read().decode("utf-8")
            detail = json.loads(body).get("error", "") or body.strip()
        except Exception:
            detail = str(exc)
        raise RuntimeError(detail or f"Agent request failed: {exc}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Agent request failed: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Agent returned invalid JSON") from exc


def request_document_advice(
    document: dict[str, Any],
    options: AgentClientOptions | None = None,
) -> str:
    options = options or AgentClientOptions()
    payload = {
        "document": document,
        "model": options.model,
        "temperature": options.temperature,
    }
    data = _post_json(f"{options.base_url}/api/document-advice", payload)
    if "error" in data:
        raise RuntimeError(data["error"])
    return str(data.get("advice", ""))


def request_document_chat(
    document: dict[str, Any],
    message: str,
    history: list[dict[str, str]] | None = None,
    categories: list[str] | None = None,
    options: AgentClientOptions | None = None,
) -> str:
    """Send one chat turn about a document; return the assistant reply."""
    options = options or AgentClientOptions()
    payload = {
        "document": document,
        "message": message,
        "history": history or [],
        "categories": categories or [],
        "model": options.model,
        "temperature": options.temperature,
    }
    data = _post_json(f"{options.base_url}/api/document-chat", payload)
    if "error" in data:
        raise RuntimeError(data["error"])
    return str(data.get("reply", ""))


def request_executive_report(
    summary: dict[str, Any],
    options: AgentClientOptions | None = None,
) -> str:
    options = options or AgentClientOptions()
    payload = {
        "summary": summary,
        "model": options.model,
        "temperature": options.temperature,
    }
    data = _post_json(f"{options.base_url}/api/executive-report", payload)
    if "error" in data:
        raise RuntimeError(data["error"])
    return str(data.get("report", ""))


def request_executive_report_stream(
    summary: dict[str, Any],
    options: AgentClientOptions | None = None,
):
    """Yield chunks from the agent's streaming executive report endpoint.

    Yields strings as they arrive (ndjson chunks with {'chunk': text}).
    """
    options = options or AgentClientOptions()
    payload = {
        "summary": summary,
        "model": options.model,
        "temperature": options.temperature,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{options.base_url}/api/executive-report-stream",
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            for raw in response:
                try:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    yield str(obj.get("chunk", ""))
                except Exception:
                    continue
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Agent request failed: {exc}") from exc
