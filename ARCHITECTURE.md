# Architecture

## System Overview

Invoice Sorter is a **local-first, desktop-and-CLI invoice organizer** that classifies PDF/image documents, extracts metadata, and routes them into category folders. The system has two primary interfaces: a command-line tool and a PySide6 desktop GUI, both backed by a unified orchestration engine.

Editable diagrams are available in
[`docs/invoice_sorter_architecture.drawio`](docs/invoice_sorter_architecture.drawio):

- **Static Structure** shows module responsibilities, local boundaries, storage,
  and optional Ollama integration.
- **Dynamic Flow** shows a deterministic processing run, progress/cancellation,
  output generation, and optional post-run agent requests.

## High-Level Components

```
┌─────────────────────────────────────────────────────────────────┐
│                       User Interfaces                           │
├─────────────────────────────────────┬───────────────────────────┤
│   CLI (invoice-sorter)              │   GUI (invoice-sorter-gui)│
│   • argparse flags                  │   • PySide6 desktop app   │
│   • Run options validation          │   • Progress & Stop button │
│   • Report/audit/log output         │   • Category editor       │
└─────────────────────────────────────┴───────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│              Orchestrator (orchestrator.py)                      │
│  • Scan input folder for PDFs/images                            │
│  • Delegate to extraction adapter                               │
│  • Classify each document (confidence scoring)                  │
│  • Route to category folder (copy/move)                         │
│  • Collect results & summary for reporting                      │
└─────────────────────────────────────────────────────────────────┘
         ↓                    ↓                    ↓
    ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐
    │ Extraction  │   │ Classifier   │   │ File Operations  │
    │ Adapter     │   │ (Confidence) │   │ (Copy/Move/Log)  │
    │             │   │              │   │                  │
    │ • Docling   │   │ • Rule-based │   │ • Safe copy/move │
    │ • Light     │   │   scorer     │   │ • Dry-run mode   │
    │ • Fallback  │   │ • Metadata   │   │ • Error handling │
    └─────────────┘   │   matching   │   └──────────────────┘
                      └──────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│           Reporting & Audit (report.py, audit_log.py)          │
│  • Build Markdown summary for tax advisor                       │
│  • Write JSONL audit log (one JSON per document)                │
│  • Write performance metrics (extraction, classification time) │
└─────────────────────────────────────────────────────────────────┘
```

## Key Modules

### Core Pipeline

| Module | Responsibility |
|--------|-----------------|
| `orchestrator.py` | Main entry point; coordinates scan → extract → classify → route |
| `extraction_adapter.py` | Abstracts Docling and light backends; selects active backend at runtime |
| `classifier.py` | Rule-based invoice classification; returns category + confidence |
| `file_operations.py` | Copy/move operations with dry-run safety and collision-resistant target names |
| `scanner.py` | File system walk; detects supported formats (PDF, JPG, PNG, TIFF) |
| `metadata_extraction.py` | Parses extracted text for vendor, dates, amounts, currency, VAT, IBAN |
| `report.py` | Generates Markdown summary and collects run statistics |
| `audit_log.py` | Writes JSONL audit trail (one line per document) |
| `performance_log.py` | Tracks extraction/classification timing and token counts |

### Configuration & Models

| Module | Responsibility |
|--------|-----------------|
| `config.py` | Loads and validates `categories.yaml` (category names, keywords, vendors) |
| `models.py` | Data classes: `DocumentResult`, `ProcessingStatus`, `InvoiceMetadata`, etc. |
| `constants.py` | Safe folder-name conversion, invoice terms, and currency-symbol mappings |

### CLI & GUI

| Module | Responsibility |
|--------|-----------------|
| `cli.py` | argparse entry point; reads flags, constructs `RunOptions`, calls orchestrator |
| `gui.py` | PySide6 desktop app; progress display, category editing, PDF/CSV export, agent client |

### AI Integration (Optional)

| Module | Responsibility |
|--------|-----------------|
| `ai_review.py` | Optional post-sort review using local Ollama; sends a privacy-filtered summary without full invoice text |
| `agent_service.py` | LangGraph/Ollama REST server for health, advice, chat, and synchronous/streaming executive reports |
| `agent_client.py` | HTTP client wrapper for agent endpoints; streaming and sync variants |

## Data Flow

### Typical Run

```
User invokes:
  invoice-sorter --input /path/to/pdfs --output /out --config categories.yaml

1. CLI parses arguments → RunOptions
2. Orchestrator scans /path/to/pdfs (recursive)
3. For each file (PDF/image):
   a. Extract text (Docling or light backend)
   b. Extract metadata (vendor, dates, amounts)
   c. Classify via rule-based scorer → category + confidence
   d. Copy file to /out/Sorted_Invoices/<category>/ (dry-run: skip copy)
4. Collect DocumentResult and RunSummary
5. Report:
   - Write /out/invoice_summary.md (category counts, manual review list)
   - Write /out/audit_log.jsonl (one JSON per document)
   - Write /out/performance_log.json (timing, token counts)
```

### GUI Workflow

```
User launches invoice-sorter-gui

1. Window initializes; agent REST server starts on 127.0.0.1:8080
2. User selects input/output folders, config, options
3. Click "Run" → Worker thread spawned (non-blocking)
4. Progress bar updates; live elapsed/ETA displayed
5. Run completes → results table populated
6. User can:
   - Double-click Category column → edit (QInputDialog dropdown or text)
   - Select rows and click "Edit Category" → apply one category to the selection
   - Click "Undo Last Change" → revert last edit
   - Click "Export Corrections" → save as CSV
   - Click "Chat / Edit" → discuss one document and edit its metadata
   - Click "Document Advice" → request a manual-review assessment
   - Click "Generate Exec PDF" → render summary as PDF
   - Click "Agent Exec Report" → stream report from LangGraph agent
   - Click "Open report" / "Open folder" / double-click source file
```

## Local Agent Integration

The in-app REST service exposes:

- `GET /api/health` for readiness.
- `POST /api/document-advice` for a one-document review assessment.
- `POST /api/document-chat` for metadata-scoped chat with history and allowed categories.
- `POST /api/executive-report` for a synchronous Markdown report.
- `POST /api/executive-report-stream` for the same report as newline-delimited JSON chunks.

The integration components are:

- **Server** (`agent_service.py`): validates JSON and routes requests to per-use-case model defaults.
- **Client** (`agent_client.py`): `request_executive_report_stream()` generator yields chunks via urllib.
- **GUI** (`gui.py`): `ExecReportWorker` (QThread) consumes stream, emits chunks to modal dialog.

All agent communication is **local HTTP** (no external service required); LangGraph agent wraps Ollama for inference.

### Model selection

Defaults are selected per workload from the models installed on the target
workstation. `deepseek-r1:8b` handles reasoning-oriented post-sort review and
document advice; `qwen3-coder:30b`, the largest installed default, handles the
longer structured executive synthesis; and `granite4:tiny-h` favors lower
latency for interactive chat. These are operational tradeoffs, not universal
benchmark rankings. Environment variables and GUI fields can override every
selection; the deterministic classifier never calls these models.

## Configuration

### Categories YAML

```yaml
categories:
  "Essen & Trinken":
    keywords: [restaurant, cafe, food]
    vendors: [RestaurantName]
  "Bürobedarf":
    keywords: [office, stationery]
    vendors: []

settings:
  manual_review_category: "Unklar / Manuell prüfen"
  confidence_threshold: 0.5
  default_currency: "EUR"
```

Loaded at startup; CLI and GUI both use the same loader (`config.load_config()`).

## Testing

- **Unit tests**: `tests/test_*.py` (pytest)
- **GUI tests**: offscreen rendering (QT_QPA_PLATFORM=offscreen)
- **Server endpoint tests**: start ephemeral server, mock internal handlers
- **Streaming tests**: mock urllib responses, verify ndjson parsing
- **CI**: GitHub Actions run Python 3.12 on Ubuntu and on the Ubuntu/macOS matrix

Run tests:
```bash
.venv/bin/python -m pytest -q
```

## Privacy & Security

1. **No network uploads**: All processing is local.
2. **Dry-run by default**: Preview before any file is touched.
3. **Copy by default**: Originals remain in place unless the user explicitly enables move mode.
4. **Metadata only**: Full invoice text is never logged or reported (only extracted fields).
5. **Optional AI features**: Ollama runs locally; privacy-filtered metadata may be sent, but never full extracted invoice text.
6. **Offline mode**: Set `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` after Docling warmup for guaranteed offline.

## Dependencies

### Core
- `PyYAML`: Config parsing
- `python-dateutil`: Date parsing
- `rich`: CLI output

### Optional
- `docling`: Layout-aware PDF extraction
- `pdfplumber`, `pypdf`, `pytesseract`, `Pillow`: Light PDF/image extraction
- `PySide6`: Desktop GUI
- `langgraph`, `langchain-core`, `pydantic`: LangGraph agent service
- `python-docx`: Planned DOCX export dependency
- `ollama`: Local LLM inference (via HTTP, not imported as library)

## Performance Characteristics

Extraction and model latency depend on document complexity, OCR use, hardware,
and the selected Ollama model. The application records per-document extraction
and processing durations plus available Ollama timing/token metrics in
`performance_log.json`. The GUI runs pipeline and model work outside the main UI
thread so progress and cancellation controls remain responsive.

## Future Considerations

1. **Persist corrections**: Option to save edits back to regenerated report/audit output or reload them.
2. **Custom extraction rules**: User-defined patterns for vendor/amount matching.
3. **DOCX export**: Alternative to Markdown report.
4. **Multi-language support**: Expand German/English metadata extraction.
5. **Cloud/network backends**: Optional remote orchestrator for shared servers.
