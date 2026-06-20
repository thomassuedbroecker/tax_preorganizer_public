"""Tests for amount/date/IBAN/invoice-number extraction (German + English)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from invoice_sorter.metadata_extraction import (
    extract_iban,
    extract_invoice_number,
    extract_metadata,
    extract_metadata_hybrid,
    extract_vendor,
    normalize_for_classification,
    parse_amount,
)


def test_normalize_for_classification_flattens_markdown():
    md = "## Rechnung\n\n| Pos | Artikel |\n| --- | --- |\n| 1 | **DSL** Internet |"
    plain = normalize_for_classification(md)
    assert "#" not in plain and "|" not in plain and "*" not in plain
    assert "DSL Internet" in plain
    assert "---" not in plain

GERMAN_INVOICE = """
Rechnung
Rechnungsnummer: 2024-0815
Rechnungsdatum: 15.03.2024
Nettobetrag 100,00 EUR
MwSt 19% 19,00 EUR
Gesamtbetrag: 119,00 EUR
IBAN DE89 3704 0044 0532 0130 00
""".strip()

ENGLISH_INVOICE = """
Invoice
Invoice Number INV-2024-77
Invoice Date 15/03/2024
Subtotal 1,037.20 USD
VAT 197.36 USD
Total 1,234.56 USD
""".strip()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.234,56", Decimal("1234.56")),  # German grouping
        ("1,234.56", Decimal("1234.56")),  # English grouping
        ("1234,56", Decimal("1234.56")),   # German decimal comma
        ("12.34", Decimal("12.34")),       # English decimal point
        ("1.234", Decimal("1234")),        # German thousands, no decimals
        ("€ 99,00", Decimal("99.00")),     # currency symbol stripped
        ("not a number", None),
    ],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_invoice_number_german():
    assert extract_invoice_number(GERMAN_INVOICE) == "2024-0815"


def test_invoice_number_english():
    assert extract_invoice_number(ENGLISH_INVOICE) == "INV-2024-77"


def test_iban_extraction():
    iban = extract_iban(GERMAN_INVOICE)
    assert iban is not None
    assert iban.startswith("DE89")
    assert " " not in iban


def test_german_metadata(config):
    m = extract_metadata(GERMAN_INVOICE, config)
    assert m.invoice_number == "2024-0815"
    assert m.invoice_date == "2024-03-15"
    assert m.gross_amount == Decimal("119.00")
    assert m.vat_amount == Decimal("19.00")  # percentage skipped
    assert m.net_amount == Decimal("100.00")
    assert m.currency == "EUR"


def test_english_metadata(config):
    m = extract_metadata(ENGLISH_INVOICE, config)
    assert m.invoice_number == "INV-2024-77"
    assert m.invoice_date == "2024-03-15"
    assert m.gross_amount == Decimal("1234.56")
    assert m.vat_amount == Decimal("197.36")
    assert m.net_amount == Decimal("1037.20")
    assert m.currency == "USD"


def test_vendor_matching_is_word_boundary_aware(config):
    # "OBI" must NOT match inside "Mobilfunk"; the real vendor is Telekom.
    text = "Rechnung von Telekom fuer DSL Internet Vertrag, Mobilfunk inklusive."
    assert extract_vendor(text, config) == "Telekom"

    # A bare "Mobilfunk" yields no vendor (no false OBI match).
    assert extract_vendor("Mobilfunk Vertrag ohne Anbieter", config) is None


def test_missing_values_stay_none(config):
    m = extract_metadata("just some random text without invoice data", config)
    assert m.invoice_number is None
    assert m.gross_amount is None
    assert m.vendor is None


def test_hybrid_metadata_falls_back_to_plain_text_for_non_amount_fields(config):
    rich = "Rechnung\nGesamtbetrag: 119,00 EUR"
    plain = (
        "Rechnung von Telekom fuer DSL Internet Vertrag. "
        "Rechnungsdatum: 15.03.2024. Gesamtbetrag: 999,00 EUR."
    )

    m = extract_metadata_hybrid(rich, plain, config)

    assert m.vendor == "Telekom"
    assert m.invoice_date == "2024-03-15"
    assert m.gross_amount == Decimal("119.00")
