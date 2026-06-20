"""Markdown report generation for the tax advisor."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re
from typing import Any

from .models import UNKNOWN, DocumentResult, ProcessingStatus

REPORT_NAME = "invoice_summary.md"

_CONFIDENCE_GUIDE = (
    "| Score | Meaning |\n"
    "|---|---|\n"
    "| 0.90 – 1.00 | Very likely correct |\n"
    "| 0.70 – 0.89 | Probably correct |\n"
    "| 0.50 – 0.69 | Needs review |\n"
    "| below 0.50 | Unclear / manual review |\n"
)

_MARKDOWN_FENCE_RE = re.compile(
    r"\A```(?:markdown|md)?[ \t]*\r?\n(?P<body>.*)\r?\n```[ \t]*\Z",
    re.DOTALL | re.IGNORECASE,
)


def normalize_markdown_fragment(text: str) -> str:
    """Remove one outer code fence from model-generated Markdown."""
    cleaned = (text or "").strip()
    match = _MARKDOWN_FENCE_RE.fullmatch(cleaned)
    return match.group("body").strip() if match else cleaned


@dataclass
class RunSummary:
    """Aggregate counters and context for one run."""

    total_scanned: int = 0
    unsupported_files: list[Path] = field(default_factory=list)
    dry_run: bool = False
    manual_review_category: str = "Unklar / Manuell prüfen"
    cancelled: bool = False
    ai_review: str | None = None
    ai_review_error: str | None = None
    ai_review_metrics: dict[str, Any] | None = None
    extraction_time_seconds: float = 0.0
    processing_time_seconds: float = 0.0

    def __post_init__(self) -> None:
        self.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")


def _cell(value) -> str:
    if value is None:
        return UNKNOWN
    if isinstance(value, Decimal):
        return str(value)
    text = str(value)
    return text.replace("|", "\\|") if text else UNKNOWN


def build_report(
    results: list[DocumentResult],
    summary: RunSummary,
    compact_table: bool = False,
) -> str:
    """Build the Markdown report. ``compact_table`` drops the wide columns
    (invoice no., VAT, net, notes) so the table fits on a PDF page."""
    manual_cat = summary.manual_review_category
    processed = [r for r in results if r.status != ProcessingStatus.FAILED]
    failed = [r for r in results if r.status == ProcessingStatus.FAILED]
    manual = [
        r for r in results
        if r.status == ProcessingStatus.MANUAL_REVIEW or r.category == manual_cat
    ]
    recognized = [
        r for r in results
        if r not in failed and r not in manual
    ]

    by_category = Counter(r.category for r in results)

    lines: list[str] = []
    a = lines.append

    a("# Invoice Summary")
    a("")
    a(f"_Generated: {summary.generated_at}_"
      + ("  •  **DRY RUN — no files were copied**" if summary.dry_run else ""))
    a("")

    # 1. Executive summary
    a("## 1. Executive summary")
    a("")
    a(f"- Total scanned files: **{summary.total_scanned}**")
    a(f"- Total processed files: **{len(processed)}**")
    a(f"- Recognized invoices: **{len(recognized)}**")
    a(f"- Unclear documents (manual review): **{len(manual)}**")
    a(f"- Failed files: **{len(failed)}**")
    a(f"- Unsupported files (ignored): **{len(summary.unsupported_files)}**")
    a(f"- Total extraction time: **{summary.extraction_time_seconds:.3f} seconds**")
    a(f"- Processing time before report output: **{summary.processing_time_seconds:.3f} seconds**")
    if summary.cancelled:
        a("- Run status: **CANCELLED — partial results only**")
    a("")

    # 7. Category summary
    a("## 2. Category summary")
    a("")
    a("| Category | Files |")
    a("|---|---:|")
    for category in sorted(by_category):
        a(f"| {category} | {by_category[category]} |")
    a("")

    # Optional local AI review
    if summary.ai_review or summary.ai_review_error:
        a("## 2b. Local AI sorting review")
        a("")
        if summary.ai_review:
            a(normalize_markdown_fragment(summary.ai_review))
            metrics = summary.ai_review_metrics or {}
            if metrics:
                a("")
                a(
                    "_Ollama metrics: "
                    f"inference {metrics.get('inference_duration_seconds', 0):.3f}s; "
                    f"prompt {metrics.get('prompt_tokens', 0)} tokens; "
                    f"output {metrics.get('output_tokens', 0)} tokens; "
                    f"total {metrics.get('total_tokens', 0)} tokens._"
                )
        else:
            a(f"_AI review unavailable: {summary.ai_review_error}_")
        a("")

    # 8. Full invoice table
    a("## 3. Full invoice table")
    a("")
    if compact_table:
        a("| File Name | Category | Vendor | Invoice Date | Gross | Currency | Confidence |")
        a("|---|---|---|---|---|---|---|")
        for r in results:
            m = r.metadata
            a("| " + " | ".join([
                _cell(r.source_path.name),
                _cell(r.category),
                _cell(m.vendor),
                _cell(m.invoice_date),
                _cell(m.gross_amount),
                _cell(m.currency),
                f"{r.confidence:.2f}",
            ]) + " |")
    else:
        a("| File Name | Category | Vendor | Invoice Date | Invoice Number | "
          "Gross Amount | VAT | Net Amount | Currency | Confidence | Notes |")
        a("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in results:
            m = r.metadata
            a("| " + " | ".join([
                _cell(r.source_path.name),
                _cell(r.category),
                _cell(m.vendor),
                _cell(m.invoice_date),
                _cell(m.invoice_number),
                _cell(m.gross_amount),
                _cell(m.vat_amount),
                _cell(m.net_amount),
                _cell(m.currency),
                f"{r.confidence:.2f}",
                _cell("; ".join(r.notes)),
            ]) + " |")
    a("")

    # 9. Manual review section
    a("## 4. Files requiring manual review")
    a("")
    if manual:
        for r in manual:
            reason = "; ".join(r.notes) or "uncertain classification"
            a(f"- `{r.source_path.name}` — {reason}")
    else:
        a("_None._")
    a("")

    # 10. Error section
    a("## 5. Errors")
    a("")
    if failed:
        for r in failed:
            err = "; ".join(r.errors) or "unknown error"
            a(f"- `{r.source_path.name}` — {err}")
    else:
        a("_None._")
    a("")

    # Unsupported files
    a("## 6. Unsupported files (ignored)")
    a("")
    if summary.unsupported_files:
        for p in summary.unsupported_files:
            a(f"- `{p.name}`")
    else:
        a("_None._")
    a("")

    # Confidence guide
    a("## 7. How to read the confidence score")
    a("")
    a(_CONFIDENCE_GUIDE)

    # 11. Notes for the tax advisor
    a("## 8. Notes for the tax advisor")
    a("")
    a("- This report is an **organizing aid**, not tax software. Every amount "
      "carries a confidence score; please verify figures against the original "
      "documents.")
    a("- Values shown as `Unknown` could not be extracted automatically and "
      "were **not** guessed.")
    a(f"- Files in **{manual_cat}** need a human decision before filing.")
    if summary.dry_run:
        a("- This was a **dry run**: no files were copied. Re-run without "
          "`--dry-run` to produce the sorted folders.")
    a("")

    return "\n".join(lines)


def write_report(output_root: Path, results: list[DocumentResult], summary: RunSummary) -> Path:
    path = Path(output_root) / REPORT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_report(results, summary), encoding="utf-8")
    return path
