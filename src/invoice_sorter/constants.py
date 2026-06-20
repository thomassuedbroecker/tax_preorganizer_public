"""Shared constants: safe folder naming and invoice-term vocabularies.

Folder names are derived from category display names by transliterating German
umlauts and stripping characters that are awkward on a filesystem.
"""

from __future__ import annotations

import re

_TRANSLIT = {
    "ä": "ae", "ö": "oe", "ü": "ue",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
    "ß": "ss",
}


def safe_folder_name(name: str) -> str:
    """Convert a category display name into a safe folder name.

    ``"Auto / Mobilität"`` -> ``"Auto_Mobilitaet"``;
    ``"Software / Cloud Services"`` -> ``"Software_Cloud_Services"``.
    """
    for src, dst in _TRANSLIT.items():
        name = name.replace(src, dst)
    name = re.sub(r"[^A-Za-z0-9]+", "_", name)
    return name.strip("_")


# Terms that signal a document is an invoice/receipt at all (German + English).
# Used both to decide "is this invoice-like?" and to feed the confidence score.
INVOICE_TERMS: tuple[str, ...] = (
    # German
    "rechnung", "rechnungsnummer", "rechnungs-nr", "rechnungsdatum",
    "belegnummer", "beleg", "gesamtbetrag", "bruttobetrag", "nettobetrag",
    "mwst", "umsatzsteuer", "ust", "zahlungsdatum", "betrag", "quittung",
    # English
    "invoice", "invoice number", "invoice date", "subtotal", "total",
    "amount due", "vat", "tax", "receipt", "payment date",
)

DEFAULT_CURRENCY_SYMBOLS = {
    "€": "EUR", "eur": "EUR", "euro": "EUR",
    "$": "USD", "usd": "USD",
    "£": "GBP", "gbp": "GBP",
    "chf": "CHF",
}
