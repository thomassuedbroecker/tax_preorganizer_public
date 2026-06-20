"""Apply manual category/metadata corrections to a DocumentResult.

Pure, GUI-free logic so it is unit-testable (and runnable in CI without PySide6).
Used by the GUI's chat/edit dialog and any future correction workflow.
"""

from __future__ import annotations

from typing import Optional

from .metadata_extraction import parse_amount
from .models import DocumentResult

_TEXT_FIELDS = ("vendor", "invoice_date", "invoice_number", "currency", "payment_date", "iban")
_AMOUNT_FIELDS = ("gross_amount", "vat_amount", "net_amount")

# Field keys this helper understands (category + editable metadata).
EDITABLE_FIELDS = ("category",) + _TEXT_FIELDS + _AMOUNT_FIELDS


def _norm_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def apply_document_edits(result: DocumentResult, edits: dict[str, Optional[str]]) -> list[str]:
    """Apply ``edits`` to ``result`` in place; return human-readable change lines.

    ``edits`` keys are any of :data:`EDITABLE_FIELDS`. Amount strings are parsed
    with the locale-aware :func:`parse_amount` (German/English). Empty strings
    clear a field (set to ``None``). Unknown keys are ignored.
    """
    changes: list[str] = []

    if "category" in edits:
        new_cat = _norm_text(edits["category"])
        if new_cat and new_cat != result.category:
            changes.append(f"category: {result.category} -> {new_cat}")
            result.category = new_cat

    meta = result.metadata
    for field in _TEXT_FIELDS:
        if field in edits:
            new = _norm_text(edits[field])
            old = getattr(meta, field)
            if new != old:
                changes.append(f"{field}: {old} -> {new}")
                setattr(meta, field, new)

    for field in _AMOUNT_FIELDS:
        if field in edits:
            raw = edits[field]
            new = parse_amount(raw) if raw not in (None, "") else None
            old = getattr(meta, field)
            if new != old:
                changes.append(f"{field}: {old} -> {new}")
                setattr(meta, field, new)

    if changes:
        result.add_note("manually corrected: " + "; ".join(changes))
    return changes
