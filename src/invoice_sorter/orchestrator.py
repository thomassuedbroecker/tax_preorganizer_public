"""Pipeline orchestration: run every file through the stages and collect results.

A failure in one file never stops the run — errors are attached to that file's
result and it is routed to manual review / the error section.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Callable

from . import ai_review as ai_review_module
from . import audit_log, file_operations, performance_log, report
from .classifier import classify
from .config import Config
from .extraction_adapter import extract_document
from .metadata_extraction import extract_metadata_hybrid
from .models import DocumentResult, ExtractionStatus, ProcessingStatus
from .routing import route
from .scanner import scan_folder


@dataclass
class RunOptions:
    input_dir: Path
    output_dir: Path
    config: Config
    dry_run: bool = False
    recursive: bool = True
    move: bool = False
    extraction_backend: str = "auto"
    ai_review: bool = False
    ai_model: str = ai_review_module.DEFAULT_OLLAMA_MODEL
    ai_base_url: str = ai_review_module.DEFAULT_OLLAMA_URL
    ai_prompt_path: Path | None = None
    ai_temperature: float = 0.2
    progress_callback: Callable[[int, int], None] | None = field(
        default=None, repr=False
    )
    cancel_check: Callable[[], bool] | None = field(default=None, repr=False)


def process_file(source: Path, options: RunOptions) -> DocumentResult:
    """Run the full per-file pipeline. Always returns a result (never raises)."""
    result = DocumentResult(source_path=source)
    config = options.config
    processing_started = perf_counter()
    try:
        extraction_started = perf_counter()
        try:
            extraction = extract_document(source, backend=options.extraction_backend)
        finally:
            result.extraction_time_seconds = round(
                perf_counter() - extraction_started, 6
            )
        # record unit_count on the result for UI/metrics
        try:
            result.unit_count = extraction.unit_count
        except Exception:
            result.unit_count = 0
        class_text = extraction.classify_text()
        # Hold the plain text for routing/length checks; amounts use rich text.
        result.text = class_text
        result.extraction_status = extraction.status
        result.backend = extraction.backend
        if extraction.error:
            result.add_error(extraction.error)

        result.metadata = extract_metadata_hybrid(extraction.text, class_text, config)
        classification = classify(class_text, result.metadata, config)
        result.confidence = classification.confidence
        for note in classification.notes:
            result.add_note(note)

        result.category = route(result, classification, config)
        if result.status != ProcessingStatus.MANUAL_REVIEW:
            # Confidently classified.
            result.status = ProcessingStatus.PENDING

        # Place the file (copy/move/dry-run).
        target = file_operations.place_file(
            source,
            options.output_dir,
            result.category,
            dry_run=options.dry_run,
            move=options.move,
        )
        result.target_path = target
        if options.dry_run:
            if result.status != ProcessingStatus.MANUAL_REVIEW:
                result.status = ProcessingStatus.DRY_RUN
        elif result.status != ProcessingStatus.MANUAL_REVIEW:
            result.status = (
                ProcessingStatus.MOVED if options.move else ProcessingStatus.COPIED
            )
    except Exception as exc:  # defensive: one bad file must not stop the run
        result.status = ProcessingStatus.FAILED
        result.add_error(f"{type(exc).__name__}: {exc}")
        if result.extraction_status == ExtractionStatus.NO_TEXT:
            result.extraction_status = ExtractionStatus.ERROR
    finally:
        result.processing_time_seconds = round(perf_counter() - processing_started, 6)

    return result


def run(options: RunOptions) -> tuple[list[DocumentResult], report.RunSummary]:
    """Scan, process, and write outputs. Returns results + summary."""
    run_started = perf_counter()
    scan = scan_folder(options.input_dir, recursive=options.recursive)

    if not options.dry_run:
        file_operations.ensure_category_dirs(options.output_dir, options.config, dry_run=False)

    total_documents = len(scan.supported)
    if options.progress_callback:
        options.progress_callback(0, total_documents)

    results: list[DocumentResult] = []
    cancelled = False
    for index, path in enumerate(scan.supported, start=1):
        if options.cancel_check and options.cancel_check():
            cancelled = True
            break
        results.append(process_file(path, options))
        # expose last-processed filename and unit_count for richer UI
        try:
            options.latest_filename = results[-1].source_path.name
            options.latest_unit_count = results[-1].unit_count
        except Exception:
            options.latest_filename = None
            options.latest_unit_count = None
        if options.progress_callback:
            options.progress_callback(index, total_documents)
        if options.cancel_check and options.cancel_check():
            cancelled = True
            break

    summary = report.RunSummary(
        total_scanned=len(scan.supported) + len(scan.unsupported),
        unsupported_files=scan.unsupported,
        dry_run=options.dry_run,
        manual_review_category=options.config.manual_review_category,
        cancelled=cancelled,
    )

    if options.ai_review:
        try:
            prompt_template = ai_review_module.DEFAULT_PROMPT_TEMPLATE
            if options.ai_prompt_path:
                prompt_template = ai_review_module.load_prompt_template(
                    options.ai_prompt_path
                )
            ai_result = ai_review_module.generate_review(
                results,
                summary,
                ai_review_module.AiReviewOptions(
                    enabled=True,
                    model=options.ai_model,
                    base_url=options.ai_base_url,
                    prompt_template=prompt_template,
                    temperature=options.ai_temperature,
                ),
            )
            summary.ai_review = ai_result.text
            summary.ai_review_metrics = ai_result.metrics
        except Exception as exc:
            summary.ai_review_error = f"{type(exc).__name__}: {exc}"

    summary.extraction_time_seconds = round(
        sum(result.extraction_time_seconds for result in results), 6
    )
    summary.processing_time_seconds = round(perf_counter() - run_started, 6)

    # Outputs (report + audit log) are always written, even on dry-run, so the
    # user can preview decisions. They live under the output folder.
    report.write_report(options.output_dir, results, summary)
    audit_log.write_audit_log(
        Path(options.output_dir) / audit_log.AUDIT_LOG_NAME, results
    )
    performance_log.write_performance_log(options.output_dir, results, summary)

    return results, summary
