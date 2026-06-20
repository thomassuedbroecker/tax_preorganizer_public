"""Append-only JSONL audit log.

Stores only extracted metadata and the placement decision — never the full
invoice text (privacy requirement). One JSON object per processed file.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import UNKNOWN, DocumentResult

AUDIT_LOG_NAME = "audit_log.jsonl"


def _fmt(value: Any) -> Any:
    if value is None:
        return UNKNOWN
    if isinstance(value, Decimal):
        return str(value)
    return value


def build_entry(result: DocumentResult) -> dict[str, Any]:
    m = result.metadata
    return {
        "source_file": str(result.source_path),
        "target_file": str(result.target_path) if result.target_path else UNKNOWN,
        "category": result.category,
        "confidence": result.confidence,
        "vendor": _fmt(m.vendor),
        "invoice_date": _fmt(m.invoice_date),
        "invoice_number": _fmt(m.invoice_number),
        "gross_amount": _fmt(m.gross_amount),
        "vat": _fmt(m.vat_amount),
        "net_amount": _fmt(m.net_amount),
        "currency": _fmt(m.currency),
        "iban": _fmt(m.iban),
        "status": result.status.value,
        "notes": "; ".join(result.notes) if result.notes else "",
    }


def write_audit_log(path: Path, results: list[DocumentResult]) -> Path:
    """Write all entries to ``path`` as JSONL. Returns the path written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for result in results:
            fh.write(json.dumps(build_entry(result), ensure_ascii=False) + "\n")
    return path
