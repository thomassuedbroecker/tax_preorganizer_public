# Changelog

All notable, user-visible changes to Invoice Sorter are documented here. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Engineering session notes, verification evidence, and next-step planning live in
[docs/HANDOFF.md](docs/HANDOFF.md); this file is the curated, user-facing subset.

## [Unreleased]

_No user-facing changes yet._

## [0.1.0] - 2026-06-20

First public release. A local-first CLI and PySide6 desktop app that scans a
folder of PDF/image invoices, extracts German/English metadata, classifies each
document into configurable categories, and writes a Markdown summary plus a JSONL
audit log — entirely on your machine.

### Added

- **CLI `invoice-sorter`**: recursive scan, metadata extraction, rule-based
  classification with a confidence score, copy-by-default routing into
  `Sorted_Invoices/<Category>/`, `--dry-run`, and `--move` opt-in.
- **Desktop GUI `invoice-sorter-gui`** (PySide6): sortable results table,
  progress with elapsed/ETA, cooperative Stop, confidence-based row coloring,
  open source file / report / folder, and CSV and PDF export.
- **Extraction backends**: Docling-first with a light (pdfplumber/pypdf +
  Tesseract OCR) fallback, selectable via `--backend auto|docling|light`. Hybrid
  mode keeps Docling-quality amounts with light-quality classification.
- **Category editing in the GUI**: single- and multi-row category edits, undo,
  and "Export Corrections" to CSV.
- **Optional local AI features (Ollama)**: post-sort review (`--ai-review`),
  document advice, per-document chat/edit, and a synchronous or streaming
  executive report through an in-app local agent service. These never change the
  rule-based classification or move files.
- **Outputs**: `invoice_summary.md`, `audit_log.jsonl`, and an anonymized
  `performance_log.json` (extraction/inference timing and token counts).
- **Tuning helper** `scripts/suggest_local_config.py` builds a git-ignored
  `categories.local.yaml` from a real folder and prints counts only.
- **Customizable AI prompt** (`config/ai_review_prompt.txt`) and configurable
  Ollama sampling temperature.

### Security & privacy

- No network access in the processing path; only extracted metadata is persisted
  — never full invoice text. Copy mode and dry-run are the safe defaults.
- Optional Ollama features run locally and receive privacy-filtered metadata
  only; Docling can be enforced fully offline after a one-time model warm-up.

### Licensing

- Released under [BSD-2-Clause](LICENSE) with aligned package metadata, bundled
  license/policy/notice files, third-party notices for every direct dependency,
  and an automated license-metadata check.
