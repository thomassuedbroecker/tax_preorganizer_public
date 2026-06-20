"""Decide the final category for a document.

Classification *suggests* a category; routing decides whether we trust it or
send the file to manual review. Keeping this separate makes the "prefer manual
review over false confidence" policy explicit and tunable.
"""

from __future__ import annotations

from .classifier import ClassificationResult
from .config import Config
from .models import (
    DocumentResult,
    ExtractionStatus,
    InvoiceMetadata,
    ProcessingStatus,
)

_MIN_USEFUL_TEXT = 30  # characters


def route(
    result: DocumentResult,
    classification: ClassificationResult,
    config: Config,
) -> str:
    """Return the final category name and annotate ``result`` with reasons.

    Sets ``result.status`` to ``MANUAL_REVIEW`` when routed to manual review.
    """
    manual = config.manual_review_category
    reasons: list[str] = []

    text = result.text or ""
    meta: InvoiceMetadata = result.metadata

    if result.extraction_status in (
        ExtractionStatus.OCR_REQUIRED,
        ExtractionStatus.BACKEND_UNAVAILABLE,
        ExtractionStatus.ERROR,
    ):
        reasons.append(f"extraction issue: {result.extraction_status.value}")
    if len(text.strip()) < _MIN_USEFUL_TEXT:
        reasons.append("little or no readable text")
    if classification.conflict:
        reasons.append("several categories match equally")
    if classification.category == "Unknown" or not classification.scores:
        reasons.append("no category keyword matched")
    if meta.vendor is None and classification.confidence < config.confidence_threshold:
        reasons.append("no vendor detected and low confidence")
    if classification.confidence < config.confidence_threshold:
        reasons.append(
            f"confidence {classification.confidence:.2f} below "
            f"threshold {config.confidence_threshold:.2f}"
        )

    if reasons:
        for r in reasons:
            result.add_note(r)
        result.status = ProcessingStatus.MANUAL_REVIEW
        return manual

    return classification.category
