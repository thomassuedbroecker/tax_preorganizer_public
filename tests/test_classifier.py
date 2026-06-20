"""Tests for rule-based classification and confidence scoring."""

from __future__ import annotations

from invoice_sorter.classifier import classify
from invoice_sorter.metadata_extraction import (
    extract_metadata,
    normalize_for_classification,
)


def test_hybrid_classifies_docling_markdown(config):
    # A Docling-style markdown table classifies correctly once normalized.
    md = "# Telekom\n\n| Produkt | Preis |\n| --- | --- |\n| DSL Internet | 50,00 EUR |"
    plain = normalize_for_classification(md)
    meta = extract_metadata(md, config)          # amounts from rich markdown
    result = classify(plain, meta, config)        # classify on plain text
    assert result.category == "Internet"
    assert meta.vendor == "Telekom"


def test_clear_classification(config):
    text = "Rechnung von Telekom für DSL Internet Vertrag, Mobilfunk inklusive."
    meta = extract_metadata(text, config)
    result = classify(text, meta, config)
    assert result.category == "Internet"
    assert result.confidence > 0.5
    assert not result.conflict


def test_vendor_drives_category(config):
    text = "Invoice from OpenAI API subscription, monthly license."
    meta = extract_metadata(text, config)
    result = classify(text, meta, config)
    assert result.category == "Software / Cloud Services"
    assert meta.vendor == "OpenAI"


def test_ambiguous_classification_is_conflict(config):
    # One Haushalt keyword and one Musik keyword -> tie.
    text = "Strom und Drums auf einer Rechnung."
    meta = extract_metadata(text, config)
    result = classify(text, meta, config)
    assert result.conflict is True


def test_unknown_document(config):
    text = "lorem ipsum dolor sit amet consectetur"
    meta = extract_metadata(text, config)
    result = classify(text, meta, config)
    assert result.category == "Unknown"
    assert result.scores == {}
    assert result.confidence < 0.5
