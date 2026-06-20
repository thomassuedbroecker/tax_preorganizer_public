"""Safe file placement into category folders.

Guarantees: never overwrite, never delete (copy is the default), resolve name
collisions with a numeric suffix (``name_001.pdf``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import Config
from .constants import safe_folder_name

OUTPUT_DIR_NAME = "Sorted_Invoices"


def category_dir(output_root: Path, category: str) -> Path:
    """Path to a category's folder under ``Sorted_Invoices``."""
    return Path(output_root) / OUTPUT_DIR_NAME / safe_folder_name(category)


def ensure_category_dirs(output_root: Path, config: Config, dry_run: bool) -> Path:
    """Create the output tree for all configured categories."""
    base = Path(output_root) / OUTPUT_DIR_NAME
    if not dry_run:
        for category in config.categories:
            (base / safe_folder_name(category.name)).mkdir(parents=True, exist_ok=True)
    return base


def unique_target_path(target_dir: Path, filename: str) -> Path:
    """Return a non-colliding path inside ``target_dir`` for ``filename``.

    ``invoice.pdf`` -> ``invoice.pdf`` or ``invoice_001.pdf``, ``invoice_002.pdf`` ...
    """
    target = target_dir / filename
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    counter = 1
    while True:
        candidate = target_dir / f"{stem}_{counter:03d}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def place_file(
    source: Path,
    output_root: Path,
    category: str,
    *,
    dry_run: bool,
    move: bool = False,
) -> Path:
    """Copy (default) or move ``source`` into the category folder.

    In ``dry_run`` mode no filesystem change is made; the would-be target path
    is still computed and returned so the report can show it.
    """
    target_dir = category_dir(output_root, category)
    if dry_run:
        # Compute a plausible target without touching the filesystem.
        return target_dir / source.name

    target_dir.mkdir(parents=True, exist_ok=True)
    target = unique_target_path(target_dir, source.name)
    if move:
        shutil.move(str(source), str(target))
    else:
        shutil.copy2(str(source), str(target))
    return target
