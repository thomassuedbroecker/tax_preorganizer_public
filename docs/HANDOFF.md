# Handoff / project status

Snapshot for whoever continues this work (e.g. Codex). Read this first.

## What this is

Local-first CLI + desktop app that scans a folder of PDF/image invoices,
extracts metadata (DE/EN), classifies into configurable categories, copies files
into category folders, and writes a Markdown report + JSONL audit log. Built for
organizing invoices for a tax advisor. **Everything runs on-machine.**

## Current status (2026-06-20)

- ✅ CLI `invoice-sorter` — end-to-end, dry-run + real run.
- ✅ Desktop GUI `invoice-sorter-gui` (PySide6) — threaded, offscreen smoke-tested.
- ✅ Extraction backends: Docling (installed) → light (pdfplumber/pypdf,
  pytesseract) → graceful manual-review. Auto-selected at runtime.
- ✅ **Hybrid extraction:** `extract_document` returns `text` (rich Docling markdown)
  and `classification_text` (plain text). Classification uses plain text;
  metadata extraction uses hybrid (rich for amounts, fallback to plain for missing
  non-monetary fields).
- ✅ Rule-based classifier + confidence + manual-review routing.
- ✅ Markdown report (11 sections) + JSONL audit log.
- ✅ `scripts/suggest_local_config.py` — builds a git-ignored `categories.local.yaml`.
- ✅ **74 pytest passing** locally; CI on `.[test]` skips GUI/agent/PDF tests
  without PySide6/langgraph/pypdf; pure tests run.
- ✅ **PDF export renders Markdown** (`render_markdown_to_pdf` in `gui.py` uses
  `QTextDocument.setMarkdown`). Model-generated AI reviews are normalized to
  remove an outer Markdown code fence before report/PDF rendering.
- ✅ **Document chat + edit:** select a row → "Chat / Edit" to chat with the local
  agent about one document and edit its category/metadata. Endpoint
  `/api/document-chat` + `run_document_chat`; client `request_document_chat`;
  GUI-free edit logic `corrections.apply_document_edits`.
- ✅ **CI fix:** agent tests `pytest.importorskip("langgraph")`; new `[agent]` extra
  (langgraph, langchain-core, pydantic).
- ✅ Hybrid manual-review verified: **38 processed, 0 unsupported, 16 manual-review, 22
  classified** on real PDFs. Docling text preserved for monetary fields.
- ✅ Docling verified on Apple Silicon (torch MPS) and **offline** with
  `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`.
- ✅ **Streaming Agent Integration (NEW):** LangGraph agent REST service runs in-app
  (`agent_service.py`). `/api/executive-report-stream` endpoint returns newline-delimited
  JSON chunks. GUI `ExecReportWorker` (QThread) consumes stream, displays in modal dialog.
- ✅ **GitHub Actions CI:** `.github/workflows/ci.yml` runs pytest on Ubuntu and
  macOS with the project's required Python 3.12.
- ✅ **Category Editing (NEW):** Double-click Category column or use "Edit Category" button
  to change. "Undo Last Change" reverts edits. "Export Corrections" saves as CSV for audit.
  Changes tracked in in-memory `CorrectionLog`.
- ✅ **Per-use-case Ollama defaults:** AI review and document advice use
  `deepseek-r1:8b`, executive reports use `qwen3-coder:30b`, and chat uses
  `granite4:tiny-h`. Each is installed locally and independently overridable by
  `OLLAMA_MODEL`, `OLLAMA_ADVICE_MODEL`, `OLLAMA_REPORT_MODEL`, or
  `OLLAMA_CHAT_MODEL`; no runtime default uses `llama3.2`.
- ✅ **Batch category editing:** Multi-select table rows and click "Edit Category"
  to apply one category to all. Edits, chat/edit, and undo use stable result
  indices so sorting the table cannot update the wrong document.
- ✅ **GUI Enhancements:** Progress shows elapsed/ETA/percent; Export CSV/PDF buttons;
  double-click source file to open; confidence-based row coloring.

## Live update log

### 2026-06-20 development-tool provenance clarification

- README and `CONTENT_PROVENANCE.md` now explicitly identify the three agentic
  development tools used in the shared VS Code workflow: **GitHub Copilot,
  OpenAI Codex, and Claude Code**.
- Added a documentation-contract test to prevent the three-tool provenance list
  from drifting between the two maintained documents.
- Verification: `.venv/bin/python -m pytest -q` → **74 passed**; license metadata
  and `git diff --check` passed.

### 2026-06-20 license and distribution validation (Codex continuation)

- Confirmed the repository `LICENSE` matches the SPDX `BSD-2-Clause` text and
  that `pyproject.toml` emits `License-Expression: BSD-2-Clause`.
- Added `MANIFEST.in` and expanded `license-files` so wheel/sdist artifacts ship
  `LICENSE`, `LICENSE_POLICY.md`, and `THIRD_PARTY_NOTICES.md`; the sdist also
  includes maintained provenance/architecture/configuration documentation.
- Explicitly excluded `config/*.local.*` after an artifact build caught that a
  wildcard could package the private local category configuration.
- Corrected the PySide6 community-wheel expression and clarified that commercial
  Qt for Python is a separately obtained distribution.
- Corrected Pillow's current identifier from the historical HPND wording to
  `MIT-CMU` based on its upstream license, and normalized the python-dateutil
  dual-license expression.
- Aligned the package author with the `LICENSE` copyright owner and documented
  the separate redistribution review required for external Ollama/model assets.
- Strengthened `scripts/check_license_metadata.py` to validate BSD clauses,
  exact dependency notice rows and expected licenses, artifact license
  declarations, manifest coverage, and private-config exclusion.
- Verification: metadata checker passed for all **14 direct dependencies/extras**;
  wheel and sdist were rebuilt and inspected; `pip check` passed; full pytest
  **73 passed**; compileall and `git diff --check` passed.
- Remaining release caveat: no resolved lockfile/SBOM is committed. Before
  distributing a bundled GUI, generate an SBOM for the exact environment and
  review PySide6/Qt, Docling transitive dependencies, and downloaded model terms.

### 2026-06-20 editable architecture diagrams (Codex continuation)

- Added `docs/invoice_sorter_architecture.drawio`, an uncompressed editable
  Draw.io file with two pages:
  - **Static Structure:** local workstation/privacy boundary, CLI/GUI,
    orchestrator and deterministic pipeline modules, outputs, agent REST service,
    direct AI review, and local Ollama.
  - **Dynamic Flow:** document-processing loop, cooperative cancellation,
    outputs, direct optional `--ai-review`, and GUI advice/chat/executive-report
    request/streaming sequences.
- Linked the diagrams from README and `ARCHITECTURE.md` and added a contract test
  that parses the XML and verifies both pages and documentation links.
- Verification: `.venv/bin/python -m pytest -q` → **73 passed**; Draw.io XML,
  compileall, and `git diff --check` passed.

### 2026-06-20 documentation/code alignment (Codex continuation)

- Documented why each workload uses a different local model and clarified that
  these are operational defaults for the installed model set, not universal
  benchmark rankings. Code comments, README, Quick Start, architecture, and
  provenance now agree on defaults, overrides, privacy boundaries, and uses.
- Aligned architecture with implemented batch editing, all five local REST
  routes (including health), Python 3.12 CI, actual dependencies, copy/move
  behavior, and measured performance telemetry. Removed stale drag/drop,
  atomic-write, Python 3.11, completed batch-edit, and report-review-only claims.
- Added `tests/test_documentation_sync.py` to guard model-default and endpoint
  documentation contracts.
- Verification: `.venv/bin/python -m pytest -q` → **72 passed**; license metadata,
  compileall, and `git diff --check` passed.

### 2026-06-20 fenced AI Markdown PDF fix (Codex continuation)

- Diagnosed the reported `invoice_summary_exec.pdf`: only the local AI review
  showed raw headings, list markers, and bold syntax because the model enclosed
  its entire response in a Markdown code fence.
- Added `normalize_markdown_fragment` at both AI-response ingestion and report
  construction, so existing/injected fenced reviews and new model responses are
  both handled safely. The default and configurable prompt now explicitly forbid
  an outer code fence.
- Strengthened report, AI-review, and real PDF-render regression coverage.
- Regenerated the local executive PDF with a compact table: **5 pages**, with no
  raw AI Markdown markers detected by PDF text extraction.
- Verification: `.venv/bin/python -m pytest -q` → **70 passed**; compileall and
  `git diff --check` passed.

### 2026-06-20 model defaults + batch category editing (Codex continuation)

- Verified the model defaults against `ollama list`: `deepseek-r1:8b` for AI
  review/advice, `qwen3-coder:30b` for executive synthesis, and
  `granite4:tiny-h` for responsive chat. Added a test proving agent functions
  route to their per-feature defaults.
- Replaced the last user-facing `llama3.2` command in `docs/QUICK_START.md`.
  Remaining occurrences are historical handoff text or isolated test fixtures,
  not runtime defaults.
- Completed batch category editing and fixed the pre-existing sorted-table row
  mapping bug for category edits, undo, and Chat/Edit.
- Updated README and Quick Start behavior descriptions.
- Verification: `.venv/bin/python -m pytest -q` → **70 passed**.

### 2026-06-20 UI test fixes (Opus session)

From a manual UI test, fixed:
- **PDF "bad outline":** the 11-column invoice table overflowed the page (every
  cell wrapped into vertical character-soup, ~31 pages). PDF now uses a compact
  7-column table (`build_report(..., compact_table=True)`) rendered **landscape at
  8pt** via `render_markdown_to_pdf` → ~2 pages, readable. Full Markdown report
  keeps all columns.
- **Document Advice dumped raw JSON:** `agent_service._clean_model_output` now
  strips `<think>...</think>` and, if a model returns a JSON object, extracts the
  human field (e.g. `tax_preparer_advice`). Applied to advice/report/chat. Advice
  and chat prompts now demand plain prose, no JSON.
- **Chat parroted the category:** chat prompt now says "answer the question, don't
  restate the category". Main lever is model size — `granite4:350m-h` is too small;
  use a larger chat model.
- **Exec report "where saved":** the streaming Agent Exec Report is now saved to
  `<output>/executive_report.md` and the dialog shows the path.
- **Suite hang (critical):** `_start_agent_server` popped `QMessageBox.critical`
  on port-in-use — a modal that blocks headless/test runs forever. Replaced with a
  non-blocking status-label update. This was hanging `pytest`.
- Tests added: `_clean_model_output`, compact-table. **67 passed.**

### 2026-06-20 PDF render fix + document chat/edit (Opus session)

- Fixed CI: two agent test modules imported `langgraph` at collection time, but CI
  installs only `.[test]`. Added `pytest.importorskip("langgraph")` to them and an
  `[agent]` extra. Verified clean `.[test]` venv: 52 passed, 5 skipped, exit 0.
- Fixed the Exec PDF bug: it wrapped raw Markdown in `<pre>` so the PDF showed
  literal `#`/`|`/`**`. Now `render_markdown_to_pdf()` uses
  `QTextDocument.setMarkdown`. Added `tests/test_exec_pdf.py` (renders, no raw
  markup; skips without PySide6/pypdf).
- Added document chat + edit:
  - `agent_service.run_document_chat()` + `/api/document-chat` endpoint (history +
    allowed categories aware).
  - `agent_client.request_document_chat()`.
  - `corrections.apply_document_edits()` (GUI-free, locale-aware amount parsing) +
    `tests/test_corrections.py`.
  - GUI "Chat / Edit" button → dialog with threaded chat (`ChatWorker`) and editable
    category/metadata that applies back to the results table and correction log.
  - Tests: chat endpoint (+ requires-message), chat client. Fixed
    `start_agent_server` to record the actually-bound port (matters for port=0).
- Synced README (install `[agent]`, GUI Chat/Edit + PDF render note).
- Surfaced real agent errors: `agent_client._post_json` now reads the server's
  `{"error": ...}` body instead of showing a bare "HTTP Error 500"; `_call_ollama`
  turns a 404 into "model 'X' not found — pull it or pick another". Added
  `tests/test_post_json_surfaces_server_error`.
- Per-feature agent models: separate GUI fields for **Advice**, **Exec Report**,
  and **Chat** (`advice_model_edit` / `report_model_edit` / `chat_model_edit`);
  the existing field is now the **AI review** model. Previously Advice/Exec Report
  ignored the model field and always used the default `llama3.2`. Also added
  `THIRD_PARTY_NOTICES.md` entries for langgraph/langchain-core/pydantic so the
  license check passes. Local suite: 65 passed.

### 2026-06-20 Streaming & Category Editing

- Implemented streaming agent endpoints in `agent_service.py`:
  - New `/api/executive-report-stream` returns newline-delimited JSON chunks.
  - New `_stream_ndjson()` helper on request handler.
  - Server streams report in 400-char chunks with 50ms inter-chunk delay.
- Added streaming client helper `request_executive_report_stream()` in `agent_client.py`:
  - Generator that yields chunks as they arrive from ndjson response.
  - Uses stdlib urllib with streaming line iteration.
- Integrated GUI streaming consumer:
  - New `ExecReportWorker` (QThread) consumes streaming generator.
  - Emits chunks via Qt signals to modal text dialog.
  - Dialog appends chunks in real-time; completion message on finish.
  - "Agent Exec Report" button now shows progressive report output.
- Added three new unit tests:
  - `test_request_executive_report_stream_reads_ndjson`: mocks urllib, verifies client parsing.
  - `test_exec_report_worker_emits_chunks_and_finishes`: mocks stream, verifies signals.
  - `test_executive_report_stream_endpoint` + `test_document_advice_endpoint`: start ephemeral server, verify endpoints.
  - All 55 tests passing.
- Created GitHub Actions CI workflow `.github/workflows/ci.yml`:
  - Current matrix: Ubuntu/macOS with Python 3.12.
  - Steps: checkout, setup Python, install deps, run pytest.
  - QT_QPA_PLATFORM=offscreen for headless GUI tests.
  - Committed to `ci/add-github-actions` branch, merged to main.
- Implemented category editing features in `gui.py`:
  - New `CorrectionLog` class tracks changes (row, old_category, new_category) with undo.
  - Double-click Category column opens QInputDialog: dropdown (from config) or free text.
  - New "Edit Category" button for selected row.
  - New "Undo Last Change" button reverts last change.
  - New "Export Corrections" button saves as `category_corrections.csv`.
  - Changes update underlying `_last_results` and table immediately.
  - Correction log cleared on each new run.
- Updated `docs/QUICK_START.md` with category editing guide.
- Merged feature branch to main; all tests passing.

### 2026-06-19 Codex continuation

- Fixed `scripts/suggest_local_config.py` so Docling/hybrid mode classifies on
  `ExtractionResult.classify_text()` while still extracting metadata and vendor
  candidates from rich text.
- Added `extract_metadata_hybrid(...)`: monetary fields stay sourced from rich
  Docling text, while missing non-monetary fields (vendor, invoice date, invoice
  number, payment date, IBAN) fall back to the plain classification text.
- Added `tests/test_suggest_local_config.py` to prevent that helper from
  regressing to rich-text classification.
- Verified `.venv/bin/python -m pytest -q` -> **35 passed**.
- First real-data hybrid dry run completed with 38 processed, 0 unsupported,
  18 manual-review, 20 classified. Light-only count under current code was still
  16 manual-review / 22 classified. The two hybrid regressions were Software /
  Cloud cases that matched the category but fell below confidence threshold
  because a non-monetary field was missing from rich text.
- After broadening the fallback to non-monetary metadata, final real-data hybrid
  dry run completed with **38 processed, 0 unsupported, 16 manual-review, 22
  classified**.
- Implemented backend selection plumbing: `extract_document(path, backend=...)`,
  `RunOptions.extraction_backend`, CLI `--backend`, and GUI Auto/Docling/Light
  combo box.
- Updated README for `--backend`, the GUI selector, and the refined hybrid
  metadata behavior.
- Verified `.venv/bin/python -m pytest -q` -> **38 passed** after backend
  selection changes.
- Added `docs/QUICK_START.md` with first-run setup, dry-run, GUI, local config,
  offline Docling, and test commands. README now links to it near the top.
- Added optional local Ollama AI review integration. It runs after deterministic
  sorting, appends a local AI sorting review to `invoice_summary.md`, and does
  not affect classification or routing. Runtime prompt is code-owned in
  `src/invoice_sorter/ai_review.py`.
- Added automatic local agent REST server startup in the GUI. The app now
  launches the agent service internally, shows its status, and makes the
  Document Advice / Executive Report buttons usable without a separate server
  process.
- Added double-click opening for source files in the GUI table. Selecting a
  row and double-clicking it opens the source invoice directly in the OS
  default viewer.
- Fixed PDF export in the GUI. `QTextDocument.print()` was replaced with
  `QTextDocument.print_()` so executive PDF generation works with the installed
  PySide6 version.
- Added CLI flags `--ai-review`, `--ai-model`, and `--ai-base-url`; GUI has a
  Local AI review checkbox plus Ollama model/URL fields.
- Verified `.venv/bin/python -m pytest -q` -> **43 passed** after AI review
  changes.
- Starting licensing transparency and GitHub Actions work. Found a license
  mismatch: root `LICENSE` is BSD-2-Clause while `pyproject.toml` declares
  Apache-2.0. The existing BSD-2-Clause license will be treated as authoritative
  and project metadata/docs will be aligned to it.
- Licensing/CI work completed: `pyproject.toml` now uses the SPDX expression
  `BSD-2-Clause` and includes `LICENSE`; added `LICENSE_POLICY.md`,
  `THIRD_PARTY_NOTICES.md`, and `CONTENT_PROVENANCE.md`.
- Added `scripts/check_license_metadata.py`. It verifies project license
  consistency, required transparency files, README links, and direct dependency
  notice coverage.
- Added `.github/workflows/tests.yml` for pushes to `main`, pull requests, and
  manual runs. It uses Python 3.12, read-only contents permission, pip caching,
  license checks, compileall, and pytest.
- Final verification: editable package build/install succeeded; license checker
  passed with 11 direct dependencies/extras covered; workflow YAML parsed;
  compileall passed; pytest -> **43 passed**.
- README test badge is pinned to the `main` branch and the top of README now
  explicitly states that the project and documentation were developed with AI
  assistance under human direction/review, with a link to provenance details.
- CLI/UI smoke verification used a synthetic blank PDF only: pytest **43 passed**;
  CLI light-backend dry run processed 1 file, produced report/audit outputs, and
  routed it to manual review; offscreen PySide6 run processed the same file,
  populated 1 table row, showed the expected summary, and enabled report/output
  controls.
- GUI launch troubleshooting: the installed executable is
  `.venv/bin/invoice-sorter-gui`; it was launched successfully with macOS GUI
  access. Quick Start and README now use the explicit virtual-environment path
  and document activation plus `python -m invoice_sorter.gui` fallbacks.
- Clarified GUI startup docs: activating `.venv` is the recommended flow because
  it contains PySide6 and the installed entry point. Direct `.venv/bin/...`
  execution remains the equivalent non-activation fallback.
- Starting performance telemetry: add per-document extraction timing and preserve
  Ollama inference durations plus prompt/output token counts in an anonymized
  `performance_log.json` and report summary.
- UI progress was added to the active scope: expose an orchestrator progress
  callback and show inspected/total document counts in the PySide6 progress bar.
- Cooperative UI cancellation was added to the active scope: Stop requests
  cancellation, finishes the current document safely, then writes partial
  report/audit/performance outputs.
- Performance/progress/cancellation work completed. Each document records
  extraction and total processing seconds; `performance_log.json` uses anonymous
  document IDs and includes extraction aggregates. Ollama metrics preserve model,
  total/load/prompt-evaluation/inference durations and prompt/output/total tokens.
- UI now shows inspected/total document progress and has a Stop button. Stop is
  cooperative (after the current document), marks the report cancelled, and
  writes partial report/audit/performance outputs. Final pytest -> **47 passed**.
- Manual-review/unidentified GUI rows now use a dark red background with white
  text instead of yellow/black; failed rows remain light red.
- ✅ UI confidence coloring: rows with confidence == 1.0 now use a dark green
  background with white text; high-confidence rows (>= 0.90) use a light
  green background.
 - ✅ GUI: added `Export CSV` button to save the table view to a CSV file.
 - ✅ GUI: added `Export CSV` button to save the table view to a CSV file.
 - ✅ GUI: added `Generate Exec PDF` (AI-assisted) to produce an executive PDF report. It uses the local AI review text (when enabled) and the standard Markdown report rendered into a PDF.
 - ✅ GUI: shows elapsed runtime during a run (processed/remaining/total plus `elapsed H:MM:SS`) and appends final elapsed time to the run summary.
- Starting customizable local AI inspection prompts: add a runtime template under
  `config/` and CLI/GUI prompt-file selection.
- Ollama temperature configuration was added to the active scope: CLI flag, GUI
  numeric control, request option, and performance metrics.
- Custom runtime AI prompt and temperature work completed. Default template is
  `config/ai_review_prompt.txt`; CLI supports `--ai-prompt` and
  `--ai-temperature`; GUI provides a prompt picker and temperature control.
- Final synthetic local-Ollama verification (`granite4:350m-h`, temperature
  0.35): extraction 0.039s, inference 1.192s, 510 prompt tokens, 252 output
  tokens, 762 total tokens. Full pytest -> **50 passed**.

## ⚠️ Privacy rules — do not break

1. `tax_input_docs/` holds **real private invoices**. It is git-ignored. **Never**
   reference its path or contents in code, tests, or committed files. **Never**
   print vendor names / amounts / filenames to the console or chat.
2. Run outputs (`Sorted_Invoices/`, `invoice_summary.md`, `audit_log.jsonl`) and
   `*.local.yaml` are git-ignored. When running on real data, send `--output` to a
   path **outside the repo** (e.g. `/tmp/...`).
3. No network in the processing path. Only extracted metadata is persisted — never
   full invoice text. Copy mode is the default; `--move` is opt-in.

## Key decisions

- **Docling-first** was chosen for extraction quality. BUT see findings below —
  light backend currently classifies better.
- **PySide6** desktop GUI (vs Streamlit/Textual).
- Engine is **UI-agnostic**: `orchestrator.run(RunOptions) -> (results, summary)`.
  `cli.py` and `gui.py` are thin renderers.
- Reuse intent (not yet wired): `docling_preprocessor_factory` (hook exists in
  `extraction_adapter._extract_with_factory`) and `pdf_extraction_macos`
  (PySide6 + Ollama patterns).

## Empirical findings (from the 38 real PDFs)

- All 38 have extractable embedded text — **none needed OCR**.
- Manual-review count: **16** (lean base config) with the light backend.
- **Generic vendor expansion made it worse (16→17)** via category ties — reverted.
  Lesson: keep the committed config lean; put real vendors in `categories.local.yaml`.
- **Docling classified worse (20 manual)** than light, because its Markdown output
  (table cells, `#` headers) disrupts keyword matching. Docling is better for
  amount/VAT extraction. → A hybrid (Docling amounts + plain-text classification)
  is the recommended next architecture step.
- The data-driven `local.yaml` (light backend) got it to **14** automatically;
  most remaining files have no machine-detectable issuer token, so the user must
  assign their own vendors once in the git-ignored file.

## How to run

```bash
# from german_tax_preorganizer/
.venv/bin/python -m pytest -q                      # tests
.venv/bin/invoice-sorter --input ./tax_input_docs --output /tmp/out --dry-run
.venv/bin/invoice-sorter-gui                       # desktop app
.venv/bin/python scripts/suggest_local_config.py --input ./tax_input_docs
```

Environment: `.venv` (Python 3.12.12) has docling 2.104.0, torch 2.12.1,
PySide6, pdfplumber/pypdf, PyYAML, python-dateutil, rich, pytest. Tesseract 5.5.1
installed (eng only; `brew install tesseract-lang` for German OCR via the light
backend).

## Suggested next steps

1. ✅ Done: hybrid verified on 38 real PDFs (16 manual-review, 22 classified).
2. ✅ Done: GUI backend selector (Auto/Docling/Light).
3. ✅ Done: Streaming agent endpoints + GUI consumer + CI workflow.
4. ✅ Done: Category editing, undo, and corrections export.
5. ✅ Done: batch category edits with sorting-safe result mapping.
6. **Persist corrections:** Option to re-run with user-edited categories or save
   edits back to audit log.
7. **DOCX export** (`[docx]` extra, `python-docx`) mirroring `report.py`.
8. **Optional Ollama tie-breaker:** Use agent to resolve manual-review files.
9. Help the user finish `categories.local.yaml` for their real vendors.
10. **Streaming response improvements:** Add progress/status messages in chunks
    (e.g., "Processing...", "Complete").

## Worktree / continuation status

The changes described in the 2026-06-20 UI fixes and Codex continuation entries
are currently **uncommitted** on `main`. Preserve the existing worktree and
review the full diff before committing. The next implementation target is
persisting corrections into regenerated report/audit output or a clearly defined
re-import format.

Earlier committed work on `main` (after merging `ci/add-github-actions`):

```
dccfcbc docs: add category editing features to QUICK_START
862cf12 feat: add Edit Category button, Undo, and export corrections log
fc6148d ci: add GitHub Actions CI matrix (OS+Python)
5300072 tests: add streaming client, ExecReportWorker, and server endpoint tests
```

Key files changed/added:
- Added: `ARCHITECTURE.md` — system design, data flow, module responsibilities.
- Added: `.github/workflows/ci.yml` — GitHub Actions matrix (Ubuntu/macOS × Python 3.12).
- Added: `tests/test_agent_streaming.py`, `tests/test_exec_stream_gui.py`, `tests/test_agent_server_endpoints.py`.
- Modified: `src/invoice_sorter/agent_service.py` (streaming endpoint + ndjson helper).
- Modified: `src/invoice_sorter/agent_client.py` (streaming client generator).
- Modified: `src/invoice_sorter/gui.py` (ExecReportWorker, CorrectionLog, category editing, undo/export).
- Modified: `docs/QUICK_START.md` (category editing guide).
- Modified: `docs/HANDOFF.md` (this file).
- Modified: `CONTENT_PROVENANCE.md` (updated AI integration notes).

Repo is on `main`. Current local verification: **74 tests passed**.
