from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from langgraph.prebuilt.chat_agent_executor import create_react_agent
from langchain_core.language_models.chat_models import AIMessage, SimpleChatModel
from langchain_core.messages.human import HumanMessage
from langchain_core.messages.system import SystemMessage
from pydantic import PrivateAttr

from .ai_review import (
    DEFAULT_ADVICE_MODEL,
    DEFAULT_CHAT_MODEL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    DEFAULT_REPORT_MODEL,
)
from .models import DocumentResult, ProcessingStatus
from .report import RunSummary

DEFAULT_AGENT_HOST = "127.0.0.1"
DEFAULT_AGENT_PORT = 8080
DEFAULT_AGENT_URL = f"http://{DEFAULT_AGENT_HOST}:{DEFAULT_AGENT_PORT}"


@dataclass
class AgentServerHandle:
    server: ThreadingHTTPServer
    thread: Thread
    host: str
    port: int

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


@dataclass
class AgentRequest:
    type: str
    payload: dict[str, Any]


def _messages_to_prompt(messages: list[Any]) -> str:
    parts: list[str] = []
    for message in messages:
        role = message.__class__.__name__.replace("Message", "").lower()
        content = getattr(message, "content", "")
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


class OllamaAgentModel(SimpleChatModel):
    model_name: str = DEFAULT_OLLAMA_MODEL
    base_url: str = DEFAULT_OLLAMA_URL
    temperature: float = 0.2
    timeout_seconds: float = 60.0
    _last_metrics: dict[str, Any] = PrivateAttr(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "ollama"

    def _call(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> str:
        prompt = _messages_to_prompt(messages)
        text, metrics = _call_ollama(
            prompt,
            self.model_name,
            self.base_url,
            self.temperature,
            self.timeout_seconds,
        )
        self._last_metrics = metrics
        return text


def _call_ollama(
    prompt: str,
    model: str,
    base_url: str,
    temperature: float,
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    url = base_url.rstrip("/") + "/api/generate"
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", "")
        except Exception:
            detail = ""
        if exc.code == 404:
            raise RuntimeError(
                f"Ollama model '{model}' not found. Pull it with `ollama pull {model}` "
                f"or choose an installed model in the Ollama model field. "
                f"({detail or exc})"
            ) from exc
        raise RuntimeError(f"Ollama request failed: {detail or exc}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Ollama request timed out") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama returned invalid JSON") from exc

    text = str(data.get("response") or "").strip()
    if not text:
        raise RuntimeError("Ollama returned an empty response")

    def seconds(field: str) -> float:
        return round(float(data.get(field) or 0) / 1_000_000_000, 6)

    prompt_tokens = int(data.get("prompt_eval_count") or 0)
    output_tokens = int(data.get("eval_count") or 0)
    metrics = {
        "model": str(data.get("model") or model),
        "temperature": temperature,
        "total_duration_seconds": seconds("total_duration"),
        "load_duration_seconds": seconds("load_duration"),
        "prompt_eval_duration_seconds": seconds("prompt_eval_duration"),
        "inference_duration_seconds": seconds("eval_duration"),
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "total_tokens": prompt_tokens + output_tokens,
    }
    return text, metrics


def _build_document_advice_prompt(document: dict[str, Any]) -> str:
    return (
        "You are a local invoice sorting assistant. Use only the JSON data below. "
        "Do not invent vendor names, dates, amounts, or file contents. "
        "Review the document metadata, category, confidence, and notes, and "
        "provide concise advice for a tax preparer on whether manual review is needed. "
        "Respond in plain prose for a person to read. Do NOT output JSON, do NOT "
        "repeat the input fields, and do NOT wrap your answer in code fences."
        "\n\n"
        "Document JSON:\n"
        f"{json.dumps(document, ensure_ascii=False, indent=2)}\n"
    )


def _build_executive_report_prompt(summary: dict[str, Any]) -> str:
    return (
        "You are an executive summary writer for tax administration. Use only the "
        "JSON data below. Do not invent values or create new invoices. "
        "Write a concise executive report in Markdown that highlights overall "
        "sorting health, risk areas, manual-review priorities, and recommendations." 
        "\n\n"
        "Summary JSON:\n"
        f"{json.dumps(summary, ensure_ascii=False, indent=2)}\n"
    )


def _document_to_payload(result: DocumentResult) -> dict[str, Any]:
    return {
        "file_name": result.source_path.name,
        "category": result.category,
        "confidence": result.confidence,
        "status": result.status.value,
        "notes": result.notes,
        "metadata": {
            "vendor": result.metadata.vendor,
            "invoice_date": result.metadata.invoice_date,
            "invoice_number": result.metadata.invoice_number,
            "gross_amount": str(result.metadata.gross_amount)
            if result.metadata.gross_amount is not None
            else None,
            "vat_amount": str(result.metadata.vat_amount)
            if result.metadata.vat_amount is not None
            else None,
            "net_amount": str(result.metadata.net_amount)
            if result.metadata.net_amount is not None
            else None,
            "currency": result.metadata.currency,
        },
    }


def _summary_to_payload(summary: RunSummary, results: list[DocumentResult]) -> dict[str, Any]:
    categories: dict[str, int] = {}
    statuses: dict[str, int] = {}
    manual_docs: list[dict[str, Any]] = []
    for result in results:
        categories[result.category] = categories.get(result.category, 0) + 1
        statuses[result.status.value] = statuses.get(result.status.value, 0) + 1
        if result.status == ProcessingStatus.MANUAL_REVIEW or result.category == summary.manual_review_category:
            manual_docs.append(_document_to_payload(result))

    return {
        "total_scanned": summary.total_scanned,
        "processed": len(results),
        "manual_review": len(manual_docs),
        "failed": sum(1 for r in results if r.status == ProcessingStatus.FAILED),
        "unsupported": len(summary.unsupported_files),
        "categories": categories,
        "statuses": statuses,
        "manual_review_documents": manual_docs,
    }


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_JSON_TEXT_KEYS = (
    "tax_preparer_advice", "advice", "reply", "answer", "response", "summary", "report",
)


def _clean_model_output(text: str) -> str:
    """Make raw model output presentable to a human.

    Strips reasoning-model ``<think>...</think>`` blocks, and if the model
    returned a JSON object (some models do), extracts the human-readable field
    instead of showing the raw JSON.
    """
    text = _THINK_RE.sub("", text or "").strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return text
        if isinstance(obj, dict):
            for key in _JSON_TEXT_KEYS:
                value = obj.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return text


def _create_agent(prompt: str, base_url: str, model: str, temperature: float) -> Any:
    llm = OllamaAgentModel(
        model_name=model,
        base_url=base_url,
        temperature=temperature,
    )
    return create_react_agent(llm, [], prompt=prompt)


def run_document_advice(
    document: dict[str, Any],
    base_url: str = DEFAULT_OLLAMA_URL,
    model: str | None = None,
    temperature: float = 0.2,
) -> str:
    model = model or DEFAULT_ADVICE_MODEL
    prompt = _build_document_advice_prompt(document)
    agent = _create_agent(prompt, base_url, model, temperature)
    state = agent.invoke({"messages": [HumanMessage(content="Please review the document.")], "remaining_steps": 5})
    return _clean_model_output(state["messages"][-1].content)


def run_executive_report(
    summary: dict[str, Any],
    base_url: str = DEFAULT_OLLAMA_URL,
    model: str | None = None,
    temperature: float = 0.2,
) -> str:
    model = model or DEFAULT_REPORT_MODEL
    prompt = _build_executive_report_prompt(summary)
    agent = _create_agent(prompt, base_url, model, temperature)
    state = agent.invoke({"messages": [HumanMessage(content="Please write the report.")], "remaining_steps": 5})
    return _clean_model_output(state["messages"][-1].content)


def _build_document_chat_prompt(
    document: dict[str, Any], categories: list[str] | None = None
) -> str:
    cat_line = ""
    if categories:
        cat_line = "Allowed categories: " + ", ".join(categories) + ". "
    return (
        "You are a local invoice sorting assistant chatting with a tax preparer "
        "about ONE document. Use only the JSON data below; do not invent vendor "
        "names, dates, amounts, or file contents. " + cat_line +
        "Answer the user's actual question directly and specifically. Do NOT just "
        "restate the current category. When asked which category fits, pick the "
        "single best one from the allowed list and explain briefly using the "
        "document's vendor/notes. Reply in plain prose; do NOT output JSON. Keep "
        "answers concise."
        "\n\n"
        "Document JSON:\n"
        f"{json.dumps(document, ensure_ascii=False, indent=2)}\n"
    )


def run_document_chat(
    document: dict[str, Any],
    message: str,
    history: list[dict[str, str]] | None = None,
    base_url: str = DEFAULT_OLLAMA_URL,
    model: str | None = None,
    temperature: float = 0.2,
    categories: list[str] | None = None,
) -> str:
    """Answer a chat turn about a single document. History is a list of
    ``{"role": "user"|"assistant", "content": str}`` dicts."""
    model = model or DEFAULT_CHAT_MODEL
    prompt = _build_document_chat_prompt(document, categories)
    agent = _create_agent(prompt, base_url, model, temperature)
    messages: list[Any] = []
    for turn in history or []:
        content = str(turn.get("content", ""))
        if turn.get("role") == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    messages.append(HumanMessage(content=message))
    state = agent.invoke({"messages": messages, "remaining_steps": 5})
    return _clean_model_output(state["messages"][-1].content)


class AgentRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream_ndjson(self, chunks: list[str]) -> None:
        # send a newline-delimited JSON stream (ndjson)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.end_headers()
        for chunk in chunks:
            payload = json.dumps({"chunk": chunk}, ensure_ascii=False).encode("utf-8") + b"\n"
            try:
                self.wfile.write(payload)
                self.wfile.flush()
            except BrokenPipeError:
                break
            time.sleep(0.05)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send_json({"status": "ok"})
        else:
            self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, status=400)
            return

        try:
            if self.path == "/api/document-advice":
                document = payload.get("document")
                if not isinstance(document, dict):
                    raise ValueError("Missing document payload")
                advice = run_document_advice(
                    document,
                    base_url=payload.get("base_url") or DEFAULT_OLLAMA_URL,
                    model=payload.get("model"),
                    temperature=float(payload.get("temperature", 0.2)),
                )
                self._send_json({"advice": advice})
            elif self.path == "/api/document-chat":
                document = payload.get("document")
                message = payload.get("message")
                if not isinstance(document, dict):
                    raise ValueError("Missing document payload")
                if not isinstance(message, str) or not message.strip():
                    raise ValueError("Missing message")
                reply = run_document_chat(
                    document,
                    message,
                    history=payload.get("history"),
                    base_url=payload.get("base_url") or DEFAULT_OLLAMA_URL,
                    model=payload.get("model"),
                    temperature=float(payload.get("temperature", 0.2)),
                    categories=payload.get("categories"),
                )
                self._send_json({"reply": reply})
            elif self.path == "/api/executive-report-stream":
                summary = payload.get("summary")
                if not isinstance(summary, dict):
                    raise ValueError("Missing summary payload")
                report_text = run_executive_report(
                    summary,
                    base_url=payload.get("base_url") or DEFAULT_OLLAMA_URL,
                    model=payload.get("model"),
                    temperature=float(payload.get("temperature", 0.2)),
                )
                # stream the report in small chunks as ndjson
                chunks: list[str] = [report_text[i : i + 400] for i in range(0, len(report_text), 400)]
                self._stream_ndjson(chunks)
            elif self.path == "/api/executive-report":
                summary = payload.get("summary")
                if not isinstance(summary, dict):
                    raise ValueError("Missing summary payload")
                report_text = run_executive_report(
                    summary,
                    base_url=payload.get("base_url") or DEFAULT_OLLAMA_URL,
                    model=payload.get("model"),
                    temperature=float(payload.get("temperature", 0.2)),
                )
                self._send_json({"report": report_text})
            else:
                self._send_json({"error": "Not found"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)


def start_agent_server(
    host: str = DEFAULT_AGENT_HOST,
    port: int = DEFAULT_AGENT_PORT,
) -> AgentServerHandle:
    server = ThreadingHTTPServer((host, port), AgentRequestHandler)
    # Record the actually-bound port (matters when port=0 is requested).
    bound_port = server.server_address[1]
    thread = Thread(
        target=server.serve_forever,
        daemon=True,
        name="InvoiceSorterAgentServer",
    )
    thread.start()
    print(f"Agent server listening at http://{host}:{bound_port}")
    return AgentServerHandle(server=server, thread=thread, host=host, port=bound_port)


def run_agent_server(
    host: str = DEFAULT_AGENT_HOST,
    port: int = DEFAULT_AGENT_PORT,
) -> None:
    server = ThreadingHTTPServer((host, port), AgentRequestHandler)
    print(f"Agent server listening at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_agent_server()
