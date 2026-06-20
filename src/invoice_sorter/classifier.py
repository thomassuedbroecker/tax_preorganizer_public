"""Transparent rule-based classifier and confidence scorer.

No LLM. Categories are scored by counting keyword and vendor matches in the
document text. Confidence is an additive model where every contributing factor
is recorded as a human-readable note, so a reviewer can always see *why* a file
landed where it did.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Config
from .constants import INVOICE_TERMS
from .metadata_extraction import count_invoice_terms
from .models import UNKNOWN, InvoiceMetadata

# Confidence weights — tuned to be conservative (prefer manual review).
_W_INVOICE_TERMS = 0.20
_W_GROSS = 0.15
_W_DATE = 0.10
_W_INVOICE_NO = 0.10
_W_VENDOR = 0.15
_W_PER_KEYWORD_HIT = 0.10
_W_KEYWORD_CAP = 0.30
_VENDOR_HIT_WEIGHT = 2  # a vendor match counts as 2 keyword hits
_TIE_PENALTY = 0.70


@dataclass
class ClassificationResult:
    category: str
    confidence: float
    scores: dict[str, int]
    conflict: bool
    notes: list[str]


def _count_hits(text_low: str, terms: tuple[str, ...]) -> int:
    """Count term occurrences using word-ish boundaries to avoid substrings."""
    total = 0
    for term in terms:
        if not term:
            continue
        pattern = r"(?<![\wäöüß])" + re.escape(term.lower()) + r"(?![\wäöüß])"
        total += len(re.findall(pattern, text_low))
    return total


def classify(text: str, metadata: InvoiceMetadata, config: Config) -> ClassificationResult:
    text_low = (text or "").lower()
    notes: list[str] = []

    scores: dict[str, int] = {}
    for category in config.categories:
        if category.name == config.manual_review_category:
            continue
        kw = _count_hits(text_low, category.keywords)
        vn = _count_hits(text_low, category.vendors) * _VENDOR_HIT_WEIGHT
        if kw + vn > 0:
            scores[category.name] = kw + vn

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_name = ranked[0][0] if ranked else UNKNOWN
    top_score = ranked[0][1] if ranked else 0
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    conflict = bool(ranked) and len(ranked) > 1 and top_score == second_score

    # --- confidence model -------------------------------------------------
    confidence = 0.0
    invoice_term_count = count_invoice_terms(text)
    if invoice_term_count > 0:
        confidence += _W_INVOICE_TERMS
        notes.append(f"{invoice_term_count} invoice term(s) found")
    if metadata.gross_amount is not None:
        confidence += _W_GROSS
        notes.append("gross amount extracted")
    if metadata.invoice_date is not None:
        confidence += _W_DATE
        notes.append("invoice date extracted")
    if metadata.invoice_number is not None:
        confidence += _W_INVOICE_NO
        notes.append("invoice number extracted")
    if metadata.vendor is not None:
        confidence += _W_VENDOR
        notes.append(f"vendor '{metadata.vendor}' matched")

    if top_score > 0:
        kw_contrib = min(_W_KEYWORD_CAP, _W_PER_KEYWORD_HIT * top_score)
        confidence += kw_contrib
        notes.append(f"category '{top_name}' matched ({top_score} hit(s))")
    else:
        notes.append("no category keyword matched")

    if conflict:
        confidence *= _TIE_PENALTY
        notes.append(
            f"category conflict: {ranked[0][0]} vs {ranked[1][0]} ({top_score} each)"
        )

    confidence = round(min(1.0, confidence), 2)

    return ClassificationResult(
        category=top_name,
        confidence=confidence,
        scores=scores,
        conflict=conflict,
        notes=notes,
    )
