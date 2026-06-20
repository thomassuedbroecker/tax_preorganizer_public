"""Tests for the manual-review routing policy."""

from __future__ import annotations

from pathlib import Path

from invoice_sorter.classifier import classify
from invoice_sorter.metadata_extraction import extract_metadata
from invoice_sorter.models import DocumentResult, ExtractionStatus, ProcessingStatus
from invoice_sorter.routing import route

CONFIDENT_TEXT = (
    "Rechnung von Telekom fuer DSL Internet Vertrag. "
    "Rechnungsnummer 12345. Rechnungsdatum 01.01.2024. "
    "Gesamtbetrag 50,00 EUR."
)


def _result(text: str) -> DocumentResult:
    r = DocumentResult(source_path=Path("x.pdf"))
    r.text = text
    r.extraction_status = ExtractionStatus.OK
    return r


def test_confident_document_keeps_category(config):
    r = _result(CONFIDENT_TEXT)
    r.metadata = extract_metadata(CONFIDENT_TEXT, config)
    classification = classify(CONFIDENT_TEXT, r.metadata, config)
    r.confidence = classification.confidence
    final = route(r, classification, config)
    assert final == "Internet"
    assert r.status != ProcessingStatus.MANUAL_REVIEW


def test_unknown_document_goes_to_manual_review(config):
    text = "lorem ipsum dolor"
    r = _result(text)
    r.metadata = extract_metadata(text, config)
    classification = classify(text, r.metadata, config)
    r.confidence = classification.confidence
    final = route(r, classification, config)
    assert final == config.manual_review_category
    assert r.status == ProcessingStatus.MANUAL_REVIEW


def test_missing_backend_forces_manual_review(config):
    r = _result(CONFIDENT_TEXT)
    r.extraction_status = ExtractionStatus.BACKEND_UNAVAILABLE
    r.metadata = extract_metadata(CONFIDENT_TEXT, config)
    classification = classify(CONFIDENT_TEXT, r.metadata, config)
    r.confidence = classification.confidence
    final = route(r, classification, config)
    assert final == config.manual_review_category
    assert r.status == ProcessingStatus.MANUAL_REVIEW
