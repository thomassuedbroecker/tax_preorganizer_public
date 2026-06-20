# Invoice Sorter

[![Tests](https://github.com/thomassuedbroecker/german_tax_preorganizer/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/thomassuedbroecker/german_tax_preorganizer/actions/workflows/tests.yml)
[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD--2--Clause-blue.svg)](LICENSE)

_Note: This project and its documentation were developed with AI assistance
(GitHub Copilot, OpenAI Codex, and Claude Code) under human direction and review. See
[CONTENT_PROVENANCE.md](CONTENT_PROVENANCE.md) for details._

## Multi-agent IDE collaboration example

This repository is also a practical example of using **three different agentic
coding plug-ins in one Visual Studio Code workspace: GitHub Copilot, OpenAI
Codex, and Claude Code. The tools do not share
their context windows or token budgets automatically. Instead,
[docs/HANDOFF.md](docs/HANDOFF.md) acts as the shared continuity document: each
agent reads the current status, continues a bounded task, records changes and
verification evidence, documents known limitations, and identifies the next
work item.

This workflow lets a developer rotate between tools when an individual context
window or token allowance is exhausted and combine their complementary
capabilities without losing project state. All resulting changes remain subject
to human review.

A **local-first** command-line tool that scans a folder of PDF and image
invoices/receipts, extracts metadata, classifies each document into configurable
categories, copies it into a category folder, and produces a Markdown summary for
a tax advisor plus a JSONL audit log.

Built for a private user organizing invoices for a tax advisor. It runs entirely
on your machine.

For the shortest setup and first dry run, see
[docs/QUICK_START.md](docs/QUICK_START.md).

For system design, architecture, data flow, and module responsibilities, see
[ARCHITECTURE.md](ARCHITECTURE.md). The editable
[Draw.io architecture diagrams](docs/invoice_sorter_architecture.drawio) contain
separate static-structure and dynamic-flow pages.

## 1. What the tool does

1. Recursively scans an input folder for `PDF, JPG, JPEG, PNG, TIFF`.
2. Extracts text (Docling-first, with a lightweight fallback; OCR for images).
3. Extracts invoice metadata: vendor, dates, invoice number, gross/VAT/net,
   currency, IBAN — **German and English** formats.
4. Classifies each file with a transparent rule-based scorer and a confidence
   score.
5. Copies files into `Sorted_Invoices/<Category>/` (copy, never move, by default).
6. Writes `invoice_summary.md`, `audit_log.jsonl`, and an anonymized
   `performance_log.json`.

## 2. Privacy model

Invoices contain sensitive personal and financial data, so:

- **No network access in the processing path.** Nothing is uploaded.
- **Only extracted metadata is stored** — the full invoice text is never written
  to the report or audit log.
- **Copy mode by default** (originals are never moved or deleted).
- **Dry-run mode** lets you preview every decision before any file is touched.
- **Uncertain results are marked** and routed to a manual-review folder.

> Note on Docling: the optional Docling backend downloads layout/table/OCR
> **models** on first use (Hugging Face + ModelScope for RapidOCR). That is a
> one-time setup download — **no invoice data leaves your machine.** After a
> one-time warm-up the tool runs **fully offline**; enforce it with:
>
> ```bash
> export HF_HUB_OFFLINE=1
> export TRANSFORMERS_OFFLINE=1
> ```
>
> Verified on Apple Silicon (torch MPS): with these set, extraction runs with no
> network access.

## 3. Installation

Requires **Python 3.12**.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .            # core (light deps)
```

Optional backends/extras:

```bash
pip install -e ".[light]"   # pdfplumber/pypdf + pytesseract image OCR (fallback)
pip install -e ".[docling]" # Docling extraction (best tables/amounts; heavy)
pip install -e ".[gui]"     # PySide6 desktop app
pip install -e ".[agent]"   # in-app LangGraph agent (chat / advice / exec report)
pip install -e ".[docx]"    # DOCX export (planned)
pip install -e ".[test]"    # pytest
```

The extraction backend is auto-selected at runtime: **Docling if installed**,
otherwise the **light** backend, otherwise files are flagged for manual review.
Check which is active with:

```bash
python -c "from invoice_sorter.extraction_adapter import active_backend; print(active_backend())"
```

## 4. Required system tools

- **Python 3.12**
- **Tesseract** — only used by the **light** backend to OCR image files /
  scanned PDFs. The **Docling** backend bundles its own OCR (RapidOCR), so
  Tesseract is not needed when Docling is installed. Without either, image files
  are flagged for manual review instead of crashing.

## 5. Installing Tesseract on macOS (light backend only)

```bash
brew install tesseract
brew install tesseract-lang   # adds German (deu); the base install is eng-only
```

## 6. Running the CLI

```bash
invoice-sorter \
  --input "/path/to/input/folder" \
  --output "/path/to/output/folder" \
  --config "config/categories.yaml" \
  --backend auto \
  --dry-run
```

Options:

| Option | Meaning |
|---|---|
| `--input` | Input folder with PDFs and images (required) |
| `--output` | Output folder for sorted invoices and reports (required) |
| `--config` | Path to category configuration (default: bundled `config/categories.yaml`) |
| `--backend` | Extraction backend: `auto`, `docling`, or `light` (default: `auto`) |
| `--dry-run` | Analyze only; do not copy files |
| `--recursive` / `--no-recursive` | Scan subfolders (default: on) |
| `--move` | Move instead of copy (default: copy — safer) |
| `--ai-review` | Append an optional local Ollama sorting review to `invoice_summary.md` |
| `--ai-model` | Ollama model for `--ai-review` (default: `$OLLAMA_MODEL` or `deepseek-r1:8b`) |
| `--ai-base-url` | Ollama URL for `--ai-review` (default: `http://127.0.0.1:11434`) |
| `--ai-prompt` | Custom AI review prompt template file; `{json_data}` inserts the inspection payload |
| `--ai-temperature` | Ollama sampling temperature from `0.0` to `2.0` (default: `0.2`) |
| `--verbose` | Print a per-file line (filenames; avoid when screen-sharing private data) |
| `--version` | Print version and exit |

## 6b. Desktop app (GUI)

A local PySide6 desktop app wraps the same engine:

```bash
source .venv/bin/activate
pip install -e ".[gui]"
invoice-sorter-gui
```

The virtual environment contains PySide6 and the installed application. Without
activating it, use `.venv/bin/invoice-sorter-gui`. You can also run
`.venv/bin/python -m invoice_sorter.gui` as a module fallback.

The GUI now launches its own local agent REST service automatically on
startup using the default host/port shown in the Agent host / Agent port fields.
The agent status label shows whether the server started successfully. Document
Advice and Executive Report become available once a run has completed, without
requiring a separate agent server process.

Pick input/output folders and a config, toggle **Dry run** (on by default),
choose a backend (**Auto**, **Docling**, or **Light**), optionally enable
**Local AI review**, then click **Run**. Results appear in a sortable table
(manual-review rows shown dark red with white text, failures light red,
high-confidence values green); double-click a row to open the source invoice
file.
Buttons open the report and output folder. The work runs in a background thread
so the window stays responsive. A progress bar shows inspected/total documents.
**Stop** requests cooperative cancellation: the current document finishes, then
partial report, audit, and performance outputs are written.

**Chat / Edit a document.** Select a row and click **Chat / Edit** to open a
dialog that lets you (a) chat with the local agent about that one document
(it answers from the document's metadata only and can suggest a category from
your config) and (b) edit the **category** and **metadata** (vendor, dates,
invoice number, gross/VAT/net, currency) and **Apply** the changes back to the
results table. Category changes are tracked in the correction log (Undo / Export
Corrections). Requires the `[agent]` extra and a local Ollama server for chat;
editing works without them. The non-GUI edit logic lives in
[corrections.py](src/invoice_sorter/corrections.py) (`apply_document_edits`).

To correct several documents at once, select multiple table rows and click
**Edit Category**. The chosen category is applied to every selected document;
edits and undo remain attached to the correct documents after table sorting.

**Models are per-feature.** The **AI review model** field drives the post-sort
review, and a separate **Agent models** row lets you pick a different Ollama
model for **Advice**, **Exec Report**, and **Chat** independently. Sensible
per-use-case defaults are used (and each is overridable by an environment
variable):

| Use case | Default model | Why this default | Environment override |
|---|---|---|---|
| AI review + general fallback | `deepseek-r1:8b` | Reasoning-focused model with a moderate local footprint for checking counts, confidence signals, and exceptions. | `OLLAMA_MODEL` |
| Document Advice | `deepseek-r1:8b` | The same reasoning behavior fits a focused decision about whether one document needs manual review. | `OLLAMA_ADVICE_MODEL` |
| Executive Report | `qwen3-coder:30b` | The largest installed default is reserved for the longer structured synthesis across the complete run summary. | `OLLAMA_REPORT_MODEL` |
| Chat | `granite4:tiny-h` | The smaller model reduces interactive turn latency while answering from one document's metadata. | `OLLAMA_CHAT_MODEL` |

These are practical defaults for the models installed on the target workstation,
not claims that one model is universally best. Available memory, response time,
language quality, and local evaluation results may justify different choices.
Environment overrides are read when the application starts; the GUI fields can
also override them for the current run.

Set them to models you have installed (`ollama list`). If a model is missing you
get a clear "pull it or choose another" message instead of an opaque error.
Reasoning-model `<think>` blocks and JSON-wrapped replies are cleaned
automatically.

**Generate Exec PDF** renders the Markdown report into a formatted PDF (headings,
tables, bold) via `QTextDocument.setMarkdown` — it no longer dumps raw Markdown.

## 7. How dry-run works

`--dry-run` runs the **entire** analysis — scan, extract, classify, route — and
writes the report and audit log so you can review decisions, but it **does not
create the `Sorted_Invoices/` tree or copy any file.** Re-run without `--dry-run`
to actually sort.

## 7b. Optional local AI review

`--ai-review` calls a local Ollama server after deterministic sorting finishes
and appends a **Local AI sorting review** section to `invoice_summary.md`.
Classification remains rule-based; the AI review does not move files or change
categories.

```bash
invoice-sorter \
  --input "/path/to/input/folder" \
  --output "/path/to/output/folder" \
  --backend auto \
  --dry-run \
  --ai-review \
  --ai-model deepseek-r1:8b \
  --ai-temperature 0.2
```

Privacy boundary: the AI review prompt is generated in application code and sends
aggregate counts, confidence signals, manual-review reasons, and limited
metadata to local Ollama. It never sends full extracted invoice text. The files
under `config/` are the only prompt templates loaded by the app.

`performance_log.json` records per-document extraction/processing time under
anonymous IDs (`doc_001`, etc.). When Ollama is enabled, it also records model,
total/load/prompt-evaluation/inference durations, and prompt/output/total token
counts returned by Ollama. The Markdown report includes total extraction time and
a compact Ollama inference/token summary.

### Customize the AI inspection prompt

The default runtime template is
[`config/ai_review_prompt.txt`](config/ai_review_prompt.txt). Copy it to the
git-ignored local override before editing:

```bash
cp config/ai_review_prompt.txt config/ai_review_prompt.local.txt
```

Keep `{json_data}` where the privacy-filtered inspection payload should be
inserted. Document IDs are pseudonymized, but the payload can contain extracted
metadata such as vendor, date, invoice number, amount, and currency for
low-confidence documents. It never contains full extracted invoice text.
If the placeholder is omitted, the application appends the JSON data after the
custom instructions. Run with:

```bash
invoice-sorter \
  --input "/path/to/input/folder" \
  --output "/path/to/output/folder" \
  --dry-run \
  --ai-review \
  --ai-model deepseek-r1:8b \
  --ai-temperature 0.2 \
  --ai-prompt config/ai_review_prompt.local.txt
```

The GUI exposes the same setting through the **AI review prompt** field and file
picker, plus an **AI temperature** control. Lower values are more deterministic;
higher values allow more variation.

## 8. Configuring categories

Categories live in [config/categories.yaml](config/categories.yaml). Each
category has `keywords` and optional `vendors`:

```yaml
categories:
  Internet:
    keywords: [Internet, DSL, Glasfaser, Router, Mobilfunk]
    vendors:  [Telekom, Vodafone, 1&1, O2]
```

Folder names are derived automatically (umlauts transliterated, e.g.
`Auto / Mobilität` → `Auto_Mobilitaet`).

**Keep private vendor names out of the repo:** copy the file to a location
outside version control (or a git-ignored `*.local.yaml`) and pass it with
`--config`. The bundled config intentionally contains only generic examples.

### Tuning on your own folder

[scripts/suggest_local_config.py](scripts/suggest_local_config.py) scans a real
folder, finds the files that land in manual review, extracts candidate vendor
tokens, auto-assigns well-known public vendors, and writes a **git-ignored**
`config/categories.local.yaml`. It prints **only counts** — your vendor names go
into the (git-ignored) file, never the console.

```bash
python scripts/suggest_local_config.py --input ./your_folder
#   add --use-docling to extract with Docling instead of the light backend
```

Then open `config/categories.local.yaml`, move the `# REVIEW` vendor tokens
under the right categories, and run with `--config config/categories.local.yaml`.

> **Hybrid extraction (implemented).** Docling's Markdown output (table cells,
> `#` headers) classifies *worse* than plain text, but extracts amounts/VAT
> *better*. So the pipeline now uses **two views**: monetary metadata comes from
> Docling's rich text, missing non-monetary metadata can fall back to plain text,
> and classification runs on a plain-text view (the light backend's text when
> available, else `normalize_for_classification()` of the Markdown). You get
> Docling-quality amounts with light-quality sorting.

## 9. Interpreting the confidence score

| Score | Meaning |
|---|---|
| 0.90 – 1.00 | Very likely correct |
| 0.70 – 0.89 | Probably correct |
| 0.50 – 0.69 | Needs review |
| below 0.50 | Unclear / manual review |

A file is routed to **Unklar / Manuell prüfen** when: text is too short / OCR is
poor, no category keyword matches, several categories tie, no vendor is detected
with low confidence, or confidence is below the configured threshold.

## 10. Known limitations

- Rule-based classification only — accuracy depends on your keyword/vendor lists.
- Vendor detection is config-driven (a configured vendor name must appear in the
  text); unknown vendors show as `Unknown`.
- No line-item extraction, no multi-page invoice merging, no duplicate detection.
- Amounts are extracted, **never computed** — if only the gross is printed, VAT
  and net stay `Unknown`.
- This is an **organizing aid, not tax software.** Verify all figures.

## 11. Future improvements

- Optional **DOCX** export for Apple Pages.
- Optional local **Ollama** assist for classification tie-breaks (augmenting, not
  replacing, the rule-based result), following the author's `pdf_extraction_macos`
  project. Current Ollama features provide post-sort review, document advice,
  document chat, and executive reports; they do not change classification. The
  `docling_preprocessor_factory` repo can be wired into
  `extraction_adapter._extract_with_factory` if preferred over plain Docling.

Done already: CLI, Docling backend, hybrid extraction, backend selection,
optional local Ollama review/advice/chat/reporting, **PySide6 desktop GUI**,
rule-based classifier, Markdown report, JSONL audit log, dry-run, real-data
tuning script.

## 12. Licensing and provenance

- Project license: [BSD 2-Clause](LICENSE)
- License and redistribution policy: [LICENSE_POLICY.md](LICENSE_POLICY.md)
- Direct dependency notices: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- AI-assisted development provenance: [CONTENT_PROVENANCE.md](CONTENT_PROVENANCE.md)

Third-party packages and optional model artifacts retain their own terms. Before
shipping a bundled application, generate a resolved dependency/SBOM report and
review the exact PySide6/Qt, Docling, OCR, and model distribution configuration.
Built wheel and source archives include the project license, license policy, and
third-party notices. The source manifest explicitly excludes private
`config/*.local.*` files.

## Project structure

```
german_tax_preorganizer/
  pyproject.toml                 # py3.12; extras: docling, light, gui, agent, docx, test
  config/
    categories.yaml              # generic, committed
    categories.local.yaml        # git-ignored, your private vendors
    ai_review_prompt.txt          # default runtime Ollama review template
  scripts/
    suggest_local_config.py      # build categories.local.yaml from a real folder
  src/invoice_sorter/
    cli.py                       # `invoice-sorter` entry point
    gui.py                       # `invoice-sorter-gui` entry point (PySide6)
    orchestrator.py              # run(): scan -> per-file pipeline -> outputs
    scanner.py                   # recursive file collection
    extraction_adapter.py        # backend selection: factory -> docling -> light
    metadata_extraction.py       # DE/EN amounts, dates, IBAN, invoice no., vendor
    classifier.py                # keyword/vendor scoring + confidence
    routing.py                   # confident category vs. manual review
    file_operations.py           # safe copy, collision-resolving names
    audit_log.py                 # JSONL writer
    performance_log.py           # anonymized extraction/Ollama timing + tokens
    report.py                    # Markdown report (RunSummary + build_report)
    config.py / constants.py / models.py
  tests/                         # pytest suite (optional-feature tests skip if unavailable)
  examples/sample_invoice_summary.md
  tax_input_docs/                # git-ignored real invoices (not in repo)
```

The engine is UI-agnostic: both `cli.py` and `gui.py` call
`orchestrator.run(RunOptions)` and render the returned `(results, summary)`.

## Development

```bash
pip install -e ".[test]"
python scripts/check_license_metadata.py
pytest
```
