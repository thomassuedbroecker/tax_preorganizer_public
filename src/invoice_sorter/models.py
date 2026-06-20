"""Data models for the invoice sorter pipeline.

Plain dataclasses only — no heavy dependencies. Amounts use ``Decimal`` so tax
figures are never subject to binary float rounding. Missing values stay ``None``
internally and are rendered as ``Unknown`` at report/audit time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional

UNKNOWN = "Unknown"


class ProcessingStatus(str, Enum):
    """Final disposition of a single file."""

    PENDING = "pending"
    COPIED = "copied"
    MOVED = "moved"
    DRY_RUN = "dry_run"
    MANUAL_REVIEW = "manual_review"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExtractionStatus(str, Enum):
    """Outcome of the text-extraction stage."""

    OK = "ok"
    OCR_USED = "ocr_used"
    OCR_REQUIRED = "ocr_required"  # image / scanned PDF but no OCR backend
    NO_TEXT = "no_text"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    ERROR = "error"


@dataclass
class InvoiceMetadata:
    """Extracted invoice fields. ``None`` means "not found" — never invented."""

    vendor: Optional[str] = None
    invoice_date: Optional[str] = None  # ISO yyyy-mm-dd
    invoice_number: Optional[str] = None
    gross_amount: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None
    currency: Optional[str] = None
    payment_date: Optional[str] = None  # ISO yyyy-mm-dd
    iban: Optional[str] = None

    def completeness(self) -> int:
        """How many of the core fields were extracted (0-5). Drives confidence."""
        core = [
            self.vendor,
            self.invoice_date,
            self.invoice_number,
            self.gross_amount,
            self.currency,
        ]
        return sum(1 for v in core if v is not None)


@dataclass
class ExtractionResult:
    """Text extracted from one document, plus how it was obtained.

    Hybrid views: ``text`` is the richest available text (Docling markdown with
    tables) used for amount/metadata extraction; ``classification_text`` is a
    plain-text view used for keyword classification (Docling markdown classifies
    worse, so we prefer plain text). When only one view exists they are equal.
    """

    text: str = ""
    classification_text: str = ""
    unit_count: int = 0  # pages / slides / sheets
    ocr_used: bool = False
    status: ExtractionStatus = ExtractionStatus.NO_TEXT
    backend: str = "none"
    error: Optional[str] = None

    def classify_text(self) -> str:
        """Text to classify on — falls back to ``text`` when not set separately."""
        return self.classification_text or self.text


@dataclass
class DocumentResult:
    """Everything we know about one input file as it flows through the pipeline."""

    source_path: Path
    metadata: InvoiceMetadata = field(default_factory=InvoiceMetadata)
    category: str = UNKNOWN
    confidence: float = 0.0
    status: ProcessingStatus = ProcessingStatus.PENDING
    extraction_status: ExtractionStatus = ExtractionStatus.NO_TEXT
    backend: str = "none"
    extraction_time_seconds: float = 0.0
    processing_time_seconds: float = 0.0
    target_path: Optional[Path] = None
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Raw text is held transiently for the in-memory pipeline only. It is never
    # written to the audit log or the report (privacy requirement).
    text: str = field(default="", repr=False)
    unit_count: int = 0

    def add_note(self, note: str) -> None:
        if note and note not in self.notes:
            self.notes.append(note)

    def add_error(self, err: str) -> None:
        if err:
            self.errors.append(err)
