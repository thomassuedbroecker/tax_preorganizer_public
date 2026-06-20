"""Tests for extraction backend selection."""

from __future__ import annotations

import pytest

from invoice_sorter import extraction_adapter
from invoice_sorter.models import ExtractionResult, ExtractionStatus


def test_extract_document_light_skips_docling(tmp_path, monkeypatch):
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    calls = []

    def fake_docling(_path):
        calls.append("docling")
        return ExtractionResult(
            text="docling",
            status=ExtractionStatus.OK,
            backend="docling",
        )

    def fake_light(_path):
        calls.append("light")
        return ExtractionResult(
            text="plain text for classification",
            status=ExtractionStatus.OK,
            backend="pdfplumber",
        )

    monkeypatch.setattr(extraction_adapter, "_extract_with_docling", fake_docling)
    monkeypatch.setattr(extraction_adapter, "_extract_pdf_light", fake_light)

    result = extraction_adapter.extract_document(pdf, backend="light")

    assert calls == ["light"]
    assert result.backend == "pdfplumber"
    assert result.classification_text == "plain text for classification"


def test_extract_document_rejects_unknown_backend(tmp_path):
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    with pytest.raises(ValueError, match="unsupported extraction backend"):
        extraction_adapter.extract_document(pdf, backend="unknown")
