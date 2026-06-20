"""End-to-end dry-run test of the orchestrator.

Text extraction is monkeypatched so the test runs without Docling/pdfplumber
installed and is deterministic.
"""

from __future__ import annotations

import json

import pytest

from invoice_sorter import orchestrator
from invoice_sorter.ai_review import AiReviewResult
from invoice_sorter.cli import build_parser
from invoice_sorter.models import ExtractionResult, ExtractionStatus, ProcessingStatus
from invoice_sorter.orchestrator import RunOptions

INTERNET_TEXT = (
    "Rechnung von Telekom fuer DSL Internet Vertrag. "
    "Rechnungsnummer 12345. Rechnungsdatum 01.01.2024. Gesamtbetrag 50,00 EUR."
)


def test_cli_ai_temperature_validation():
    parser = build_parser()
    args = parser.parse_args(
        ["--input", "in", "--output", "out", "--ai-temperature", "0.75"]
    )
    assert args.ai_temperature == 0.75

    with pytest.raises(SystemExit):
        parser.parse_args(
            ["--input", "in", "--output", "out", "--ai-temperature", "2.5"]
        )


@pytest.fixture
def fake_extract(monkeypatch):
    def _fake(path, backend="auto"):
        return ExtractionResult(
            text=INTERNET_TEXT, unit_count=1, status=ExtractionStatus.OK,
            backend="fake",
        )

    monkeypatch.setattr(orchestrator, "extract_document", _fake)


def test_dry_run_writes_outputs_but_no_copies(tmp_path, config, fake_extract):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "telekom.pdf").write_bytes(b"%PDF-1.4 fake")
    output_dir = tmp_path / "out"

    options = RunOptions(
        input_dir=input_dir, output_dir=output_dir, config=config, dry_run=True
    )
    results, summary = orchestrator.run(options)

    assert len(results) == 1
    assert results[0].category == "Internet"
    assert results[0].status == ProcessingStatus.DRY_RUN

    # Reports were written...
    assert (output_dir / "invoice_summary.md").exists()
    assert (output_dir / "audit_log.jsonl").exists()
    assert (output_dir / "performance_log.json").exists()
    # ...but no file was actually copied (no Sorted_Invoices tree on dry-run).
    assert not (output_dir / "Sorted_Invoices").exists()


def test_real_run_copies_into_category(tmp_path, config, fake_extract):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "telekom.pdf").write_bytes(b"%PDF-1.4 fake")
    output_dir = tmp_path / "out"

    options = RunOptions(
        input_dir=input_dir, output_dir=output_dir, config=config, dry_run=False
    )
    results, summary = orchestrator.run(options)

    assert results[0].status == ProcessingStatus.COPIED
    copied = output_dir / "Sorted_Invoices" / "Internet" / "telekom.pdf"
    assert copied.exists()

    # Audit log is valid JSONL with one entry.
    lines = (output_dir / "audit_log.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["category"] == "Internet"
    assert entry["status"] == "copied"


def test_run_options_pass_extraction_backend(tmp_path, config, monkeypatch):
    seen = []

    def _fake(path, backend="auto"):
        seen.append(backend)
        return ExtractionResult(
            text=INTERNET_TEXT,
            unit_count=1,
            status=ExtractionStatus.OK,
            backend="fake",
        )

    monkeypatch.setattr(orchestrator, "extract_document", _fake)
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "telekom.pdf").write_bytes(b"%PDF-1.4 fake")

    options = RunOptions(
        input_dir=input_dir,
        output_dir=tmp_path / "out",
        config=config,
        dry_run=True,
        extraction_backend="light",
    )

    orchestrator.run(options)

    assert seen == ["light"]


def test_ai_review_failure_is_nonfatal(tmp_path, config, fake_extract, monkeypatch):
    def fail_review(*_args, **_kwargs):
        raise RuntimeError("Ollama unavailable")

    monkeypatch.setattr(orchestrator.ai_review_module, "generate_review", fail_review)
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "telekom.pdf").write_bytes(b"%PDF-1.4 fake")

    options = RunOptions(
        input_dir=input_dir,
        output_dir=tmp_path / "out",
        config=config,
        dry_run=True,
        ai_review=True,
    )

    results, summary = orchestrator.run(options)

    assert len(results) == 1
    assert "Ollama unavailable" in summary.ai_review_error
    report = (tmp_path / "out" / "invoice_summary.md").read_text()
    assert "AI review unavailable" in report


def test_progress_and_cancellation_write_partial_outputs(
    tmp_path, config, fake_extract
):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    for index in range(3):
        (input_dir / f"invoice-{index}.pdf").write_bytes(b"%PDF-1.4 fake")

    progress = []
    cancelled = False

    def on_progress(completed, total):
        nonlocal cancelled
        progress.append((completed, total))
        if completed == 1:
            cancelled = True

    options = RunOptions(
        input_dir=input_dir,
        output_dir=tmp_path / "out",
        config=config,
        dry_run=True,
        progress_callback=on_progress,
        cancel_check=lambda: cancelled,
    )

    results, summary = orchestrator.run(options)

    assert len(results) == 1
    assert summary.cancelled is True
    assert progress == [(0, 3), (1, 3)]
    assert (tmp_path / "out" / "invoice_summary.md").exists()
    assert (tmp_path / "out" / "audit_log.jsonl").exists()
    assert (tmp_path / "out" / "performance_log.json").exists()
    assert "CANCELLED" in (tmp_path / "out" / "invoice_summary.md").read_text()


def test_ollama_metrics_are_written_to_performance_log(
    tmp_path, config, fake_extract, monkeypatch
):
    metrics = {
        "model": "test-model",
        "inference_duration_seconds": 1.25,
        "prompt_tokens": 100,
        "output_tokens": 25,
        "total_tokens": 125,
    }
    monkeypatch.setattr(
        orchestrator.ai_review_module,
        "generate_review",
        lambda *_args, **_kwargs: AiReviewResult("Review text", metrics),
    )
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "invoice.pdf").write_bytes(b"%PDF-1.4 fake")

    orchestrator.run(
        RunOptions(
            input_dir=input_dir,
            output_dir=tmp_path / "out",
            config=config,
            dry_run=True,
            ai_review=True,
        )
    )

    performance = json.loads(
        (tmp_path / "out" / "performance_log.json").read_text()
    )
    assert performance["ollama"]["inference_duration_seconds"] == 1.25
    assert performance["ollama"]["total_tokens"] == 125
    assert "source_file" not in json.dumps(performance)
