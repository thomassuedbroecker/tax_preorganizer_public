#!/usr/bin/env python3
"""Verify repository license metadata and notice coverage."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SPDX = "BSD-2-Clause"
EXPECTED_COPYRIGHT_OWNER = "Thomas Südbröcker"
REQUIRED_FILES = (
    "LICENSE",
    "LICENSE_POLICY.md",
    "THIRD_PARTY_NOTICES.md",
    "CONTENT_PROVENANCE.md",
)
REQUIRED_DISTRIBUTION_LICENSE_FILES = (
    "LICENSE",
    "LICENSE_POLICY.md",
    "THIRD_PARTY_NOTICES.md",
)
EXPECTED_DEPENDENCY_LICENSES = {
    "PyYAML": "MIT",
    "python-dateutil": "Apache-2.0 OR BSD-3-Clause",
    "rich": "MIT",
    "pdfplumber": "MIT",
    "pypdf": "BSD-3-Clause",
    "pytesseract": "Apache-2.0",
    "Pillow": "MIT-CMU",
    "docling": "MIT",
    "PySide6": "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
    "python-docx": "MIT",
    "langgraph": "MIT",
    "langchain-core": "MIT",
    "pydantic": "MIT",
    "pytest": "MIT",
}


def _dependency_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9_.-]+", requirement)
    return match.group(0) if match else requirement


def main() -> int:
    errors: list[str] = []
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject.get("project", {})

    if project.get("license") != EXPECTED_SPDX:
        errors.append(
            f"pyproject.toml project.license must be {EXPECTED_SPDX!r}"
        )
    authors = project.get("authors", [])
    if not any(author.get("name") == EXPECTED_COPYRIGHT_OWNER for author in authors):
        errors.append(
            "pyproject.toml author must match the LICENSE copyright owner: "
            f"{EXPECTED_COPYRIGHT_OWNER}"
        )

    license_files = project.get("license-files", [])
    for relative_path in REQUIRED_DISTRIBUTION_LICENSE_FILES:
        if relative_path not in license_files:
            errors.append(
                "pyproject.toml project.license-files must include "
                f"{relative_path}"
            )

    for relative_path in REQUIRED_FILES:
        if not (ROOT / relative_path).is_file():
            errors.append(f"missing required licensing file: {relative_path}")

    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    if not license_text.startswith("BSD 2-Clause License"):
        errors.append("LICENSE does not contain the expected BSD 2-Clause text")
    if f"Copyright (c) 2026, {EXPECTED_COPYRIGHT_OWNER}" not in license_text:
        errors.append("LICENSE copyright owner does not match project metadata")
    for required_clause in (
        "Redistributions of source code must retain",
        "Redistributions in binary form must reproduce",
        'THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"',
    ):
        if required_clause not in license_text:
            errors.append(f"LICENSE is missing BSD-2-Clause text: {required_clause}")

    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    dependency_groups = [project.get("dependencies", [])]
    dependency_groups.extend(project.get("optional-dependencies", {}).values())
    dependencies = {
        _dependency_name(requirement)
        for group in dependency_groups
        for requirement in group
    }
    for dependency in sorted(dependencies, key=str.lower):
        row_pattern = (
            rf"(?mi)^\|\s*{re.escape(dependency)}\s*\|[^|]*\|\s*([^|]+?)\s*\|"
        )
        row_match = re.search(row_pattern, notices)
        if not row_match:
            errors.append(
                f"direct dependency missing from THIRD_PARTY_NOTICES.md: {dependency}"
            )
            continue
        expected_license = EXPECTED_DEPENDENCY_LICENSES.get(dependency)
        if expected_license is None:
            errors.append(f"no expected license configured for dependency: {dependency}")
        elif expected_license.lower() not in row_match.group(1).lower():
            errors.append(
                f"license mismatch for {dependency}: expected {expected_license!r}, "
                f"notice has {row_match.group(1).strip()!r}"
            )

    stale_license_entries = set(EXPECTED_DEPENDENCY_LICENSES) - dependencies
    for dependency in sorted(stale_license_entries, key=str.lower):
        errors.append(f"license expectation has no matching direct dependency: {dependency}")

    manifest_path = ROOT / "MANIFEST.in"
    if not manifest_path.is_file():
        errors.append("missing source-distribution manifest: MANIFEST.in")
    else:
        manifest = manifest_path.read_text(encoding="utf-8")
        for relative_path in REQUIRED_FILES:
            if f"include {relative_path}" not in manifest:
                errors.append(f"MANIFEST.in does not include {relative_path}")
        if "recursive-exclude config *.local.*" not in manifest:
            errors.append("MANIFEST.in must exclude private config/*.local.* files")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for relative_path in REQUIRED_FILES:
        if relative_path not in readme:
            errors.append(f"README.md does not link to {relative_path}")

    if errors:
        print("License metadata check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        f"License metadata OK: {EXPECTED_SPDX}; "
        f"{len(dependencies)} direct dependencies/extras covered."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
