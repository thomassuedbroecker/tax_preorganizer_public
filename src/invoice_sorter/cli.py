"""Command-line interface for the invoice sorter."""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .ai_review import DEFAULT_OLLAMA_MODEL, DEFAULT_OLLAMA_URL
from .config import ConfigError, load_config
from .extraction_adapter import EXTRACTION_BACKENDS, active_backend
from .orchestrator import RunOptions, run
from .performance_log import PERFORMANCE_LOG_NAME

_DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "categories.yaml"


def _temperature(value: str) -> float:
    try:
        temperature = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("temperature must be a number") from exc
    if not 0.0 <= temperature <= 2.0:
        raise argparse.ArgumentTypeError("temperature must be between 0.0 and 2.0")
    return temperature


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invoice-sorter",
        description="Local-first invoice sorter for tax preparation. "
        "Scans a folder of PDFs/images, classifies invoices, copies them into "
        "category folders, and writes a Markdown report + JSONL audit log.",
    )
    parser.add_argument("--input", required=True, help="Input folder with PDFs and images")
    parser.add_argument("--output", required=True, help="Output folder for sorted invoices and reports")
    parser.add_argument("--config", default=str(_DEFAULT_CONFIG), help="Path to category configuration (YAML/JSON)")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only; do not copy files")
    parser.add_argument(
        "--backend",
        choices=EXTRACTION_BACKENDS,
        default="auto",
        help="Extraction backend: auto/docling prefer Docling with light fallback; light skips Docling",
    )
    parser.add_argument(
        "--recursive", action=argparse.BooleanOptionalAction, default=True,
        help="Scan subfolders (default: on; use --no-recursive to disable)",
    )
    parser.add_argument(
        "--move", action="store_true",
        help="Move files instead of copying (default: copy; copy is safer)",
    )
    parser.add_argument(
        "--ai-review",
        action="store_true",
        help="Append an optional local Ollama review to the Markdown report",
    )
    parser.add_argument(
        "--ai-model",
        default=os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        help="Ollama model for --ai-review (default: $OLLAMA_MODEL or deepseek-r1:8b)",
    )
    parser.add_argument(
        "--ai-base-url",
        default=os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL),
        help="Ollama base URL for --ai-review (default: http://127.0.0.1:11434)",
    )
    parser.add_argument(
        "--ai-prompt",
        help="Path to a custom AI review prompt template; use {json_data} for payload",
    )
    parser.add_argument(
        "--ai-temperature",
        type=_temperature,
        default=0.2,
        help="Ollama sampling temperature from 0.0 to 2.0 (default: 0.2)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print more details")
    parser.add_argument("--version", action="version", version=f"invoice-sorter {__version__}")
    return parser


def _print_summary(results, summary, options, verbose: bool) -> None:
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        by_cat = Counter(r.category for r in results)
        table = Table(title="Invoice Sorter — Summary")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        selected_backend = (
            active_backend() if options.extraction_backend == "auto"
            else options.extraction_backend
        )
        table.add_row("Extraction backend", selected_backend)
        table.add_row("Mode", "DRY RUN" if summary.dry_run else ("MOVE" if options.move else "COPY"))
        table.add_row("Total scanned", str(summary.total_scanned))
        table.add_row("Processed", str(len(results)))
        table.add_row("Unsupported (ignored)", str(len(summary.unsupported_files)))
        table.add_row("Extraction time", f"{summary.extraction_time_seconds:.3f}s")
        if summary.cancelled:
            table.add_row("Run status", "CANCELLED (partial results)")
        console.print(table)

        cat_table = Table(title="By category")
        cat_table.add_column("Category")
        cat_table.add_column("Files", justify="right")
        for cat in sorted(by_cat):
            cat_table.add_row(cat, str(by_cat[cat]))
        console.print(cat_table)
    except ImportError:  # rich not installed — plain fallback
        selected_backend = (
            active_backend() if options.extraction_backend == "auto"
            else options.extraction_backend
        )
        print(f"Backend: {selected_backend}  Mode: "
              f"{'DRY RUN' if summary.dry_run else ('MOVE' if options.move else 'COPY')}")
        print(f"Scanned: {summary.total_scanned}  Processed: {len(results)}  "
              f"Unsupported: {len(summary.unsupported_files)}")

    if verbose:
        for r in results:
            print(f"  {r.source_path.name} -> {r.category} "
                  f"(conf {r.confidence:.2f}, {r.status.value})")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    input_dir = Path(args.input).expanduser()
    output_dir = Path(args.output).expanduser()

    if not input_dir.is_dir():
        print(f"error: input folder does not exist: {input_dir}", file=sys.stderr)
        return 2

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    options = RunOptions(
        input_dir=input_dir,
        output_dir=output_dir,
        config=config,
        dry_run=args.dry_run,
        recursive=args.recursive,
        move=args.move,
        extraction_backend=args.backend,
        ai_review=args.ai_review,
        ai_model=args.ai_model,
        ai_base_url=args.ai_base_url,
        ai_prompt_path=Path(args.ai_prompt).expanduser() if args.ai_prompt else None,
        ai_temperature=args.ai_temperature,
    )

    results, summary = run(options)
    _print_summary(results, summary, options, verbose=args.verbose)

    report_path = output_dir / "invoice_summary.md"
    print(f"\nReport:    {report_path}")
    print(f"Audit log: {output_dir / 'audit_log.jsonl'}")
    print(f"Performance: {output_dir / PERFORMANCE_LOG_NAME}")
    if summary.dry_run:
        print("Dry run — no files were copied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
