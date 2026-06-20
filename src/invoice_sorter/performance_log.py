"""Write anonymized extraction and local AI performance metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import DocumentResult
from .report import RunSummary

PERFORMANCE_LOG_NAME = "performance_log.json"


def build_performance_log(
    results: list[DocumentResult], summary: RunSummary
) -> dict[str, Any]:
    extraction_times = [r.extraction_time_seconds for r in results]
    processing_times = [r.processing_time_seconds for r in results]
    return {
        "generated_at": summary.generated_at,
        "run": {
            "documents": len(results),
            "total_scanned": summary.total_scanned,
            "dry_run": summary.dry_run,
            "processing_time_seconds": summary.processing_time_seconds,
        },
        "extraction": {
            "total_seconds": round(sum(extraction_times), 6),
            "average_seconds": round(
                sum(extraction_times) / len(extraction_times), 6
            ) if extraction_times else 0.0,
            "max_seconds": round(max(extraction_times), 6) if extraction_times else 0.0,
            "documents": [
                {
                    "document_id": f"doc_{index:03d}",
                    "backend": result.backend,
                    "extraction_time_seconds": result.extraction_time_seconds,
                    "processing_time_seconds": result.processing_time_seconds,
                }
                for index, result in enumerate(results, start=1)
            ],
        },
        "ollama": summary.ai_review_metrics or {
            "enabled": False,
        },
        "processing": {
            "total_document_seconds": round(sum(processing_times), 6),
            "average_document_seconds": round(
                sum(processing_times) / len(processing_times), 6
            ) if processing_times else 0.0,
        },
    }


def write_performance_log(
    output_root: Path, results: list[DocumentResult], summary: RunSummary
) -> Path:
    path = Path(output_root) / PERFORMANCE_LOG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_performance_log(results, summary), indent=2),
        encoding="utf-8",
    )
    return path
