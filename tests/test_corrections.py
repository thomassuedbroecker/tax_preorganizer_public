"""Tests for manual category/metadata corrections."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from invoice_sorter.corrections import apply_document_edits
from invoice_sorter.models import DocumentResult, InvoiceMetadata


def _result() -> DocumentResult:
    r = DocumentResult(source_path=Path("x.pdf"))
    r.category = "Unklar / Manuell prüfen"
    r.metadata = InvoiceMetadata(vendor=None, gross_amount=None, currency=None)
    return r


def test_apply_category_change():
    r = _result()
    changes = apply_document_edits(r, {"category": "Internet"})
    assert r.category == "Internet"
    assert any("category" in c for c in changes)


def test_apply_metadata_edits_parse_amounts():
    r = _result()
    apply_document_edits(r, {
        "vendor": "Telekom",
        "gross_amount": "1.234,56",   # German locale
        "currency": "EUR",
    })
    assert r.metadata.vendor == "Telekom"
    assert r.metadata.gross_amount == Decimal("1234.56")
    assert r.metadata.currency == "EUR"


def test_empty_string_clears_field():
    r = _result()
    r.metadata.vendor = "Wrong"
    apply_document_edits(r, {"vendor": ""})
    assert r.metadata.vendor is None


def test_no_change_returns_empty():
    r = _result()
    r.category = "Internet"
    changes = apply_document_edits(r, {"category": "Internet"})
    assert changes == []


def test_unknown_keys_ignored():
    r = _result()
    changes = apply_document_edits(r, {"nonsense": "x"})
    assert changes == []
