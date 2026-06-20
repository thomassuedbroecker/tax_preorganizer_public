"""Tests for optional local AI review generation."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from invoice_sorter.ai_review import (
    AiReviewOptions,
    build_prompt,
    generate_review,
    load_prompt_template,
)
from invoice_sorter.models import DocumentResult, InvoiceMetadata, ProcessingStatus
from invoice_sorter.report import RunSummary


def _result() -> DocumentResult:
    result = DocumentResult(source_path=Path("/private/input/vendor-secret.pdf"))
    result.category = "Internet"
    result.confidence = 0.42
    result.status = ProcessingStatus.MANUAL_REVIEW
    result.text = "FULL EXTRACTED PRIVATE TEXT MUST NOT LEAK"
    result.metadata = InvoiceMetadata(
        vendor="Telekom",
        invoice_date="2024-03-15",
        invoice_number="INV-1",
        gross_amount=Decimal("50.00"),
        currency="EUR",
    )
    result.add_note("confidence 0.42 below threshold 0.50")
    return result


def test_build_prompt_uses_aggregate_data_not_full_text_or_paths():
    prompt = build_prompt([_result()], RunSummary(total_scanned=1))

    assert "FULL EXTRACTED PRIVATE TEXT" not in prompt
    assert "vendor-secret.pdf" not in prompt
    assert "/private/input" not in prompt
    assert "manual_review" in prompt
    assert "doc_001" in prompt


def test_custom_prompt_template_receives_privacy_filtered_json(tmp_path):
    path = tmp_path / "review.txt"
    path.write_text("CUSTOM REVIEW\n{json_data}", encoding="utf-8")

    prompt = build_prompt(
        [_result()],
        RunSummary(total_scanned=1),
        load_prompt_template(path),
    )

    assert prompt.startswith("CUSTOM REVIEW")
    assert "doc_001" in prompt
    assert "FULL EXTRACTED PRIVATE TEXT" not in prompt
    assert "vendor-secret.pdf" not in prompt


def test_generate_review_parses_ollama_response(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return (
                b'{"model":"llama3.2","response":"```markdown\\n## Overall result\\nLooks consistent.\\n```",'
                b'"total_duration":2500000000,"load_duration":500000000,'
                b'"prompt_eval_count":120,"prompt_eval_duration":600000000,'
                b'"eval_count":40,"eval_duration":1400000000}'
            )

    def fake_urlopen(request, timeout):
        assert timeout == 3
        assert request.full_url == "http://127.0.0.1:11434/api/generate"
        request_data = json.loads(request.data)
        assert request_data["options"]["temperature"] == 0.65
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = generate_review(
        [_result()],
        RunSummary(total_scanned=1),
        AiReviewOptions(enabled=True, timeout_seconds=3, temperature=0.65),
    )

    assert "Looks consistent." in result.text
    assert "```" not in result.text
    assert result.metrics["inference_duration_seconds"] == 1.4
    assert result.metrics["prompt_tokens"] == 120
    assert result.metrics["output_tokens"] == 40
    assert result.metrics["total_tokens"] == 160
    assert result.metrics["temperature"] == 0.65
