# Changelog

## Unreleased — licensing validation

- Confirmed the project license and package metadata as `BSD-2-Clause`.
- Included `LICENSE`, `LICENSE_POLICY.md`, and `THIRD_PARTY_NOTICES.md` in wheel
  and source distributions while excluding private `config/*.local.*` files.
- Validated all 14 direct dependency/extra notice entries and corrected Pillow
  to `MIT-CMU`, python-dateutil to `Apache-2.0 OR BSD-3-Clause`, and the PySide6
  community-wheel license expression.
- Documented separate redistribution review for Qt/PySide6, Docling artifacts,
  Ollama, and local model weights.
- Strengthened automated license, manifest, copyright-owner, and notice checks.

## 2026-06-20 — GUI & reporting improvements

- UI: added `Export CSV` button to save the current table view as CSV.
- UI: added `Generate Exec PDF` to render the Markdown report (with optional AI review text) to PDF.
- UI: improved confidence coloring: `confidence == 1.0` now dark green with white text; `>= 0.90` remains light green.
- UI: richer progress display: processed / remaining / total, percent complete, ETA, current filename, units (pages), elapsed time, and token count when available.
- Added elapsed time tracking and final elapsed time in summary.
- Tests: verified — all tests pass (50 passed).
