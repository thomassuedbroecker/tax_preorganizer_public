"""Conservative invoice metadata extraction for German and English documents.

Design rule: never invent data. Every extractor returns ``None`` when it is not
confident, and the caller renders that as ``Unknown``. Amounts are parsed into
``Decimal`` with locale-aware separator handling (German ``1.234,56`` vs English
``1,234.56``).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from dateutil import parser as date_parser

from .config import Config
from .constants import DEFAULT_CURRENCY_SYMBOLS, INVOICE_TERMS
from .models import InvoiceMetadata

# A number token: 1.234,56 | 1,234.56 | 1234,56 | 1234.56 | 1234
_AMOUNT_RE = r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"

_CURRENCY_RE = re.compile(r"(€|\$|£|EUR|USD|GBP|CHF|euro)", re.IGNORECASE)

# Date tokens: 31.12.2024 | 31/12/2024 | 2024-12-31 | 31. Dezember 2024
_DATE_RE = re.compile(
    r"\b(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}"
    r"|\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}"
    r"|\d{1,2}\.?\s+(?:Jan|Feb|Mär|Mar|Apr|Mai|May|Jun|Jul|Aug|Sep|Okt|Oct|Nov|Dez|Dec)[a-zäöü]*\.?\s+\d{2,4})\b",
    re.IGNORECASE,
)

_IBAN_RE = re.compile(r"\b([A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30})\b")

_INVOICE_NO_LABELS = (
    "rechnungsnummer", "rechnungs-nr", "rechnungs nr", "rechnung nr",
    "rechnung-nr", "belegnummer", "beleg-nr", "invoice number", "invoice no",
    "invoice #", "invoice-no",
)

_GROSS_LABELS = (
    "gesamtbetrag", "bruttobetrag", "brutto", "rechnungsbetrag", "gesamtsumme",
    "gesamt", "zu zahlen", "zahlbetrag", "amount due", "total", "grand total",
)
_VAT_LABELS = (
    "mehrwertsteuer", "umsatzsteuer", "mwst", "ust", "vat", "tax", "steuer",
)
_NET_LABELS = (
    "nettobetrag", "netto", "zwischensumme", "subtotal", "net amount", "net",
)

_INVOICE_DATE_LABELS = ("rechnungsdatum", "invoice date", "datum", "date")
_PAYMENT_DATE_LABELS = (
    "zahlungsdatum", "payment date", "fällig", "faellig", "due date", "bezahlt am",
)


def normalize_text(text: str) -> str:
    """Collapse whitespace; keep the original casing for display extraction."""
    if not text:
        return ""
    text = text.replace(" ", " ")  # non-breaking space
    return re.sub(r"[ \t]+", " ", text)


def normalize_for_classification(text: str) -> str:
    """Flatten Markdown so keyword matching is not disrupted.

    Docling outputs Markdown (``| cell |``, ``# heading``, ``**bold**``, ``---``
    rules) which can fence or glue tokens. This reduces it to plain text with
    single spaces, which classifies far better than raw Markdown.
    """
    if not text:
        return ""
    text = re.sub(r"[|#>*_`]", " ", text)   # markdown punctuation -> space
    text = re.sub(r"-{2,}", " ", text)        # table rule rows ---
    return re.sub(r"\s+", " ", text).strip()


def parse_amount(raw: str) -> Optional[Decimal]:
    """Parse a localized amount string into ``Decimal``.

    Handles German (``1.234,56``) and English (``1,234.56``) grouping. Returns
    ``None`` when the token is not a parseable amount.
    """
    if raw is None:
        return None
    s = re.sub(r"[^\d.,]", "", raw).strip()
    if not s or not any(ch.isdigit() for ch in s):
        return None

    if "," in s and "." in s:
        # The right-most separator is the decimal separator.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Comma only: decimal if 1-2 trailing digits, else thousands grouping.
        tail = s.split(",")[-1]
        if len(tail) in (1, 2) and s.count(",") == 1:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        # Dot only: 1.234 style grouping -> integer; otherwise decimal point.
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")
        # else leave as-is (e.g. 12.34)

    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def detect_currency(text: str) -> Optional[str]:
    m = _CURRENCY_RE.search(text)
    if not m:
        return None
    return DEFAULT_CURRENCY_SYMBOLS.get(m.group(1).lower())


def count_invoice_terms(text: str) -> int:
    low = text.lower()
    return sum(1 for term in INVOICE_TERMS if term in low)


def _iter_label_ends(low: str, label: str):
    """Yield end positions of ``label`` in ``low`` with a left word boundary.

    The boundary stops ``total`` from matching inside ``subtotal`` (etc.).
    """
    pattern = re.compile(r"(?<![a-zäöüß])" + re.escape(label.lower()))
    for m in pattern.finditer(low):
        yield m.end()


def _amount_near_label(text: str, labels: tuple[str, ...]) -> Optional[Decimal]:
    """Find the first amount appearing shortly after any of the given labels."""
    low = text.lower()
    for label in labels:
        for end in _iter_label_ends(low, label):
            window = text[end: end + 60]
            for m in re.finditer(_AMOUNT_RE, window):
                # Skip percentages (e.g. the "19" in "MwSt 19% 19,00").
                if window[m.end(): m.end() + 1] == "%":
                    continue
                amount = parse_amount(m.group(0))
                if amount is not None:
                    return amount
    return None


def _value_near_label(text: str, labels: tuple[str, ...], pattern: str) -> Optional[str]:
    low = text.lower()
    for label in labels:
        for end in _iter_label_ends(low, label):
            window = text[end: end + 60]
            m = re.search(pattern, window)
            if m:
                return m.group(1).strip()
    return None


def extract_invoice_number(text: str) -> Optional[str]:
    return _value_near_label(
        text, _INVOICE_NO_LABELS, r"[:\s#.\-]*([A-Za-z0-9][A-Za-z0-9\-/]{2,})"
    )


def _parse_date(token: str) -> Optional[str]:
    token = token.strip().rstrip(".")
    try:
        # German invoices are day-first; ISO (yyyy-...) is handled automatically.
        dt = date_parser.parse(token, dayfirst=True, fuzzy=True)
    except (ValueError, OverflowError):
        return None
    return dt.date().isoformat()


def extract_date(text: str, labels: tuple[str, ...]) -> Optional[str]:
    """First date found near a label; falls back to None (no blind guessing)."""
    low = text.lower()
    for label in labels:
        for end in _iter_label_ends(low, label):
            window = text[end: end + 40]
            m = _DATE_RE.search(window)
            if m:
                parsed = _parse_date(m.group(1))
                if parsed:
                    return parsed
    return None


def extract_iban(text: str) -> Optional[str]:
    m = _IBAN_RE.search(text)
    if not m:
        return None
    return re.sub(r"\s+", "", m.group(1))


def extract_vendor(text: str, config: Config) -> Optional[str]:
    """Vendor detection is config-driven: a configured vendor name found in the
    text wins. We deliberately do not guess from arbitrary lines.

    Matching is word-boundary aware so a short vendor token (e.g. ``OBI``) does
    not match inside an unrelated word (e.g. ``M``**``obi``**``lfunk``).
    """
    low = text.lower()
    for category in config.categories:
        for vendor in category.vendors:
            pattern = r"(?<![\wäöüß])" + re.escape(vendor.lower()) + r"(?![\wäöüß])"
            if re.search(pattern, low):
                return vendor
    return None


def extract_metadata(text: str, config: Config) -> InvoiceMetadata:
    """Run all extractors and assemble an :class:`InvoiceMetadata`."""
    text = normalize_text(text)
    if not text:
        return InvoiceMetadata()

    invoice_date = extract_date(text, _INVOICE_DATE_LABELS)
    if invoice_date is None:
        # Last resort: the first date-like token anywhere (still a real date).
        m = _DATE_RE.search(text)
        if m:
            invoice_date = _parse_date(m.group(1))

    return InvoiceMetadata(
        vendor=extract_vendor(text, config),
        invoice_date=invoice_date,
        invoice_number=extract_invoice_number(text),
        gross_amount=_amount_near_label(text, _GROSS_LABELS),
        vat_amount=_amount_near_label(text, _VAT_LABELS),
        net_amount=_amount_near_label(text, _NET_LABELS),
        currency=detect_currency(text) or config.default_currency,
        payment_date=extract_date(text, _PAYMENT_DATE_LABELS),
        iban=extract_iban(text),
    )


def extract_metadata_hybrid(
    rich_text: str, classification_text: str, config: Config
) -> InvoiceMetadata:
    """Extract rich metadata, with non-monetary fallback from plain text.

    Docling markdown is better for amounts/tables, but configured vendor tokens,
    dates, and identifiers can be easier to match in the plain text view.
    Monetary fields stay sourced from the rich extraction view.
    """
    metadata = extract_metadata(rich_text, config)
    if not classification_text or classification_text == rich_text:
        return metadata

    fallback = extract_metadata(classification_text, config)
    for field_name in (
        "vendor",
        "invoice_date",
        "invoice_number",
        "payment_date",
        "iban",
    ):
        if getattr(metadata, field_name) is None:
            setattr(metadata, field_name, getattr(fallback, field_name))
    return metadata
