"""Tests for Markdown report generation."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from invoice_sorter.models import (
    DocumentResult,
    InvoiceMetadata,
    ProcessingStatus,
)
from invoice_sorter.report import RunSummary, build_report


def _sample_results():
    ok = DocumentResult(source_path=Path("telekom.pdf"))
    ok.category = "Internet"
    ok.confidence = 0.82
    ok.status = ProcessingStatus.COPIED
    ok.metadata = InvoiceMetadata(
        vendor="Telekom", invoice_date="2024-03-15", invoice_number="12345",
        gross_amount=Decimal("50.00"), currency="EUR",
    )

    unclear = DocumentResult(source_path=Path("scan.png"))
    unclear.category = "Unklar / Manuell prüfen"
    unclear.status = ProcessingStatus.MANUAL_REVIEW
    unclear.add_note("little or no readable text")

    failed = DocumentResult(source_path=Path("broken.pdf"))
    failed.status = ProcessingStatus.FAILED
    failed.add_error("corrupt PDF")
    return [ok, unclear, failed]


def test_report_contains_all_sections():
    results = _sample_results()
    summary = RunSummary(total_scanned=3, dry_run=False)
    md = build_report(results, summary)

    assert "# Invoice Summary" in md
    assert "## 1. Executive summary" in md
    assert "## 2. Category summary" in md
    assert "## 3. Full invoice table" in md
    assert "Files requiring manual review" in md
    assert "## 5. Errors" in md
    assert "Notes for the tax advisor" in md

    # Data shows up.
    assert "telekom.pdf" in md
    assert "Telekom" in md
    assert "scan.png" in md
    assert "corrupt PDF" in md
    # Missing values rendered as Unknown, never invented.
    assert "Unknown" in md


def test_compact_table_drops_wide_columns():
    results = _sample_results()
    summary = RunSummary(total_scanned=3)
    full = build_report(results, summary)
    compact = build_report(results, summary, compact_table=True)
    # Full table keeps the wide columns...
    assert "Net Amount" in full
    assert "Invoice Number" in full
    assert "Notes |" in full
    # ...the compact table (for PDF) drops them but keeps key columns.
    assert "Net Amount" not in compact
    assert "Invoice Number" not in compact
    assert "Gross" in compact
    assert "Confidence" in compact
    assert "Telekom" in compact


def test_dry_run_banner():
    summary = RunSummary(total_scanned=0, dry_run=True)
    md = build_report([], summary)
    assert "DRY RUN" in md


def test_report_includes_ai_review_when_present():
    summary = RunSummary(
        total_scanned=1,
        ai_review="```markdown\n## Overall result\nLooks **usable**.\n```",
        ai_review_metrics={
            "inference_duration_seconds": 1.25,
            "prompt_tokens": 100,
            "output_tokens": 25,
            "total_tokens": 125,
        },
    )
    md = build_report(_sample_results()[:1], summary)

    assert "## 2b. Local AI sorting review" in md
    assert "```markdown" not in md
    assert "## Overall result" in md
    assert "Looks **usable**." in md
    assert "inference 1.250s" in md
    assert "total 125 tokens" in md


def test_report_includes_ai_review_error_when_present():
    summary = RunSummary(total_scanned=1, ai_review_error="RuntimeError: unavailable")
    md = build_report(_sample_results()[:1], summary)

    assert "## 2b. Local AI sorting review" in md
    assert "AI review unavailable" in md


def test_write_report(tmp_path):
    from invoice_sorter.report import write_report

    summary = RunSummary(total_scanned=3)
    path = write_report(tmp_path, _sample_results(), summary)
    assert path.exists()
    assert path.name == "invoice_summary.md"
