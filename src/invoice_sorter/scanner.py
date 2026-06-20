"""Recursive folder scanner.

Collects supported invoice files and records everything else as "unsupported"
so the report can list ignored files. The output folder (``Sorted_Invoices``)
is skipped to avoid re-ingesting already-sorted files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .file_operations import OUTPUT_DIR_NAME

SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


@dataclass
class ScanResult:
    supported: list[Path]
    unsupported: list[Path]


def scan_folder(input_dir: Path, recursive: bool = True) -> ScanResult:
    """Return supported and unsupported files under ``input_dir``."""
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input folder does not exist: {input_dir}")

    iterator = input_dir.rglob("*") if recursive else input_dir.glob("*")
    supported: list[Path] = []
    unsupported: list[Path] = []

    for path in sorted(iterator):
        if path.is_dir():
            continue
        if OUTPUT_DIR_NAME in path.parts:
            continue  # never ingest our own output
        if path.name.startswith("."):
            continue  # skip hidden/system files
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            supported.append(path)
        else:
            unsupported.append(path)

    return ScanResult(supported=supported, unsupported=unsupported)
