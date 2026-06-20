# Architecture Review — Invoice Sorter `v0.1.0`

_Conducted by **Bob** (IBM Bob — Claude Code architecture-reviewer mode) · 2026-06-20_

* **SDLC Phase:** Post-initial release / active development (v0.1.0 public, Unreleased section open)
* **Review Scope:** Full codebase — all 7 architecture dimensions
* **Skill Set Applied:** Business Alignment · Security/Threat Modeling · Scalability/Performance · Architecture Patterns · Maintainability/Technical Debt · Documentation · Twelve-Factor Compliance

---

## How this review was conducted

### Reviewer

This review was produced by **Bob**, IBM's senior software architect AI assistant
running inside Visual Studio Code as part of the project's multi-agent IDE
collaboration workflow (alongside GitHub Copilot, OpenAI Codex, Claude Code and IBM Bob).
Bob operates in **architecture-reviewer mode**, a specialised persona that applies
seven structured review skills to a codebase and produces findings in a
standardised format.

### Method

1. **Repository exploration** — Bob read every source file in `src/invoice_sorter/`,
   the full test suite under `tests/`, all configuration (`config/categories.yaml`,
   `pyproject.toml`), the CI workflow (`.github/workflows/tests.yml`), and all
   documentation files (`README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`,
   `CONTENT_PROVENANCE.md`, `THIRD_PARTY_NOTICES.md`, `LICENSE_POLICY.md`,
   `docs/HANDOFF.md`, `docs/QUICK_START.md`). No file was summarised without being
   read; findings are grounded in the actual source text.

2. **Seven-skill framework** — Each dimension below maps to one review skill. Bob
   applies the skill's checklist to the evidence gathered in step 1, then produces
   structured findings in the format: ✅ Achieved / ⚠️ Concerns / ❌ Not Achieved /
   💡 Recommendations.

   | Skill | What it examines |
   |---|---|
   | Business Alignment | Goals, quality attributes, stated constraints vs. actual design |
   | Security & Threat Modeling | Attack surface, data-flow trust boundaries, sensitive-data handling |
   | Scalability & Performance | Throughput, memory, latency, concurrency model |
   | Architecture Patterns | Pipeline design, separation of concerns, coupling, abstractions |
   | Maintainability & Technical Debt | Code duplication, module size, testability, CI hygiene |
   | Documentation | Completeness, accuracy, provenance, licence notices |
   | Twelve-Factor Compliance | Cloud-native readiness across all 12 factors |

3. **Prioritised backlog** — All findings are ranked P1 (High) → P3 (Low) by
   impact and collected into a single table at the end of the document for use as
   a work backlog.

4. **No code was changed** during this review session. The findings are recorded
   here and cross-referenced in [`docs/HANDOFF.md`](HANDOFF.md) so that any
   subsequent agent or human can pick up individual items as bounded tasks.

### Artefacts produced

| Artefact | Location |
|---|---|
| This review document | `docs/ARCHITECTURE_REVIEW.md` |
| Reference link from architecture doc | `ARCHITECTURE.md` (top callout block) |
| Handoff session entry with backlog checklist | `docs/HANDOFF.md` |

---

## Executive Summary

Invoice Sorter is a well-conceived, privacy-first local tool. The core pipeline is clean,
testable, and internally consistent. Privacy guarantees are structurally enforced (no text in
logs, copy-by-default, dry-run default). The architecture has a clear separation between
deterministic and probabilistic processing. **The main risks are architectural boundary leakage
in the agent tier, single-threaded sequential processing that will become a bottleneck at scale,
hard-coded Python 3.12 pin, and the absence of input sanitisation before text passes to local
LLM prompts.**

| Dimension | Score | Summary |
|---|---|---|
| Business Alignment | ✅ Strong | Goals, constraints, and design all match |
| Security & Threat Modeling | ⚠️ Moderate | Prompt injection possible; IBAN in audit log; no input size limits |
| Scalability & Performance | ⚠️ Moderate | Sequential per-file loop; all results held in RAM; no pagination |
| Architecture Patterns | ✅ Good | Pipeline pattern well-implemented; agent tier has rough edges |
| Maintainability | ✅ Good | Clean modules; a few debt items in the agent and GUI |
| Documentation | ✅ Strong | Exceptional for a v0.1.0; minor gaps only |
| Twelve-Factor Compliance | ⚠️ Partial | Hardwired defaults; GUI bootstraps a server in-process |

---

## 1. Business Alignment

### ✅ Achieved

- **Privacy-by-architecture:** raw text is never persisted (documented in `models.py:108`),
  IBAN and extracted amounts do land in the audit log but never full OCR output — this is
  explicitly intentional.
- **Dry-run-first UX** matches the stated "safe defaults" goal.
- **Transparency:** every classification decision is accompanied by human-readable notes written
  by the classifier, enabling the stated "organizing aid, not tax software" positioning.
- **Offline guarantee:** the Docling model warm-up story plus `HF_HUB_OFFLINE` guidance is
  documented end-to-end.
- **Bilingual (DE/EN)** metadata extraction aligns with the stated German tax preparation use case.

### ⚠️ Concerns

- **IBAN is written to `audit_log.jsonl`** (`audit_log.py:41`). IBAN is a financial identifier
  subject to data-protection considerations. Whether its presence in a flat JSON log aligns with
  the privacy model should be explicitly reviewed and documented.
- **`requires-python = "==3.12.*"`** (`pyproject.toml:10`) blocks installation under CPython
  3.13+ without a release. There is no forward-compatibility note.
- **No stated SLA or performance budget:** the architecture document does not state acceptable
  latency bounds for Docling extraction, which varies wildly by hardware.

### 💡 Recommendations

1. Add a one-line clarification to `ARCHITECTURE.md` under Privacy & Security confirming that
   IBAN in the audit log is intentional and what the data lifecycle expectation is (e.g. "local
   only, purge with output folder").
2. Relax `requires-python` to `>=3.12` once 3.13 compatibility has been verified — the current
   `==3.12.*` pin produces installation errors on newer Python without user action.

---

## 2. Security & Threat Modeling

### ✅ Achieved

- No outbound network calls during the deterministic pipeline path.
- Full invoice text is never included in any persisted file or AI payload — structurally
  enforced, not just documented.
- The agent server binds to `127.0.0.1` only (`agent_service.py:30-32`) — no remote exposure.
- Config loading uses `yaml.safe_load` (`config.py:56`), preventing YAML deserialization attacks.
- File collision resolution never overwrites (`file_operations.py:32-46`) — no silent data loss.

### ❌ Not Achieved / Gaps

**P1 — Prompt Injection (High)**
Extracted metadata (vendor name, invoice number) flows directly into LLM prompts via
`json.dumps` without sanitisation in both `ai_review.py:169` and `agent_service.py:162-173`. A
maliciously crafted invoice containing a vendor name like `"Ignore all previous instructions
and..."` would be injected verbatim into the model prompt. Since this is a local model (Ollama),
the primary risk is confused output or fraudulent-looking AI review reports, not remote
exfiltration — but it is a real integrity risk.

**P2 — No Input File Size Limits (Medium)**
`scanner.py` collects all supported files recursively with no size check. A very large PDF
(hundreds of MB) will be passed directly to Docling or pdfplumber with no memory guard before
the extraction call in `orchestrator.py:53`. This can cause OOM on low-memory hardware.

**P3 — IBAN Written to Audit Log (Medium)**
`audit_log.py:41` writes IBAN verbatim. While the log is local-only, it contains a financial
identifier that should be explicitly scoped or optionally redacted.

**P4 — Agent HTTP Server Has No Authentication (Low-Medium)**
`agent_service.py:441` starts an unauthenticated HTTP server. Because it binds to loopback
only, the threat is limited to other local processes. A shared-secret token header would close
this gap.

**P5 — Full Absolute Path in Audit Log (Low)**
`audit_log.py:30` writes `str(result.source_path)` — the full absolute path including user home
directory segments. If the audit log is shared with a tax advisor, it leaks local directory
structure.

### 💡 Recommendations

1. **Prompt injection mitigation:** Truncate and strip control characters from all metadata
   fields before they enter prompt templates. A simple `_sanitise_for_prompt(value, max_chars=200)`
   helper that strips non-printable characters and limits length would reduce the risk
   significantly.
2. **File size guard in scanner:** Add a configurable `max_file_bytes` check in `scan_folder`
   (default: e.g. 50 MB) that routes oversized files to manual review rather than OOM.
3. **Audit log IBAN redaction:** Consider writing only the last 4 characters of IBAN (e.g.
   `DE**...1234`) or making IBAN logging opt-in.
4. **Agent server token:** Add an optional shared-secret header (`X-Agent-Token`) verified in
   `AgentRequestHandler.do_POST`. Generate on server start and pass to the GUI client.
5. **Relative paths in audit log:** Consider logging only `result.source_path.name` (just the
   filename) rather than the full absolute path.

---

## 3. Scalability & Performance

### ✅ Achieved

- Per-file timing is captured in `performance_log.json`, enabling users to identify slow
  documents.
- Cooperative cancellation is supported in the orchestrator loop (`orchestrator.py:124-138`).
- GUI processing runs in a worker thread, keeping the UI responsive.
- Docling's MPS acceleration on Apple Silicon is explicitly called out as a fast-path.

### ⚠️ Concerns

**Throughput Ceiling — Sequential Processing (High for large batches)**
The core loop in `orchestrator.run()` is strictly sequential: one file at a time,
single-threaded. Docling extraction is CPU/GPU-bound and I/O-bound. For 500+ invoices this can
take hours. There is no worker pool, no `concurrent.futures`, no async pipeline.

**All Results Held in RAM (Medium)**
`results: list[DocumentResult]` accumulates all objects in memory before `write_report` and
`write_audit_log` are called. Each `DocumentResult` also holds `text` (the full extracted
text). For large batches with Docling markdown output, this can be substantial.

**`unique_target_path` Linear Probe (Low)**
`file_operations.unique_target_path()` probes the filesystem with an incrementing counter. For
a category with thousands of files with the same base name, this becomes O(n) filesystem calls.

**Streaming Simulation (Low)**
The "streaming" executive report in `agent_service._stream_ndjson()` is not real streaming — it
runs the full Ollama inference synchronously, then slices the result into 400-char chunks with
50ms sleep. This is client-visible latency deception rather than true streaming.

### 💡 Recommendations

1. **Optional parallel extraction:** Add a `max_workers` option to `RunOptions` and wrap the
   file loop with `concurrent.futures.ThreadPoolExecutor`. Start with `max_workers=1` as the
   default (no behaviour change), making parallelism opt-in.
2. **Stream-write audit log:** Open `audit_log.jsonl` in append mode and write each entry
   immediately after `process_file` returns. This also provides durability on crash.
3. **Bound in-memory text:** After metadata extraction and classification are complete, clear
   `result.text` — it is already excluded from audit log and report.
4. **True streaming for Ollama:** Use Ollama's `"stream": true` API and emit each token chunk
   as it arrives, rather than buffering the full response.

---

## 4. Architecture Patterns

### ✅ Achieved

- **Pipeline pattern** cleanly implemented: `scan → extract → classify → route → place`. Each
  stage is a pure function with well-typed inputs and outputs.
- **Strategy pattern** for extraction backends: `_extract_with_factory → _extract_with_docling
  → _extract_pdf_light` provides transparent fallback with no conditional spaghetti at the call
  site.
- **Data classes** as value objects throughout — all core types are plain dataclasses with no
  implicit state.
- **UI/engine separation:** both `cli.py` and `gui.py` call the same
  `orchestrator.run(RunOptions)`, ensuring the core pipeline is interface-agnostic.
- **Idempotent output:** dry-run produces the same report/audit artifacts without side effects.
- **Config validation at load time** (`config.py:49`) — malformed config fails fast before any
  file is touched.

### ⚠️ Concerns

**Agent Service Couples Two Concerns (Medium)**
`agent_service.py` fuses HTTP routing, prompt engineering, Ollama API calls, and LangGraph agent
orchestration into one 474-line file. As new endpoints are added, this will grow hard to
maintain.

**`RunOptions` Is Mutated at Runtime (Low)**
`orchestrator.run()` adds `latest_filename` and `latest_unit_count` as dynamic attributes to
`RunOptions`. `RunOptions` is a `@dataclass` — adding undeclared attributes at runtime bypasses
the type system and can confuse static analysis.

**`_call_ollama` Is Duplicated (Medium)**
The Ollama HTTP client function exists independently in both `ai_review.py` and
`agent_service.py` with nearly identical logic. Any bug fix must be applied in two places.

### 💡 Recommendations

1. **Extract an `OllamaClient` class** shared between `ai_review.py` and `agent_service.py`.
2. **Move progress state out of `RunOptions`:** Introduce a `RunState` dataclass that the
   orchestrator fills and the GUI polls — keep `RunOptions` immutable.
3. **Split `agent_service.py`** into:
   - `agent_handlers.py` (HTTP routing + request validation)
   - `agent_prompts.py` (prompt builders)
   - `ollama_client.py` (shared HTTP calls)

---

## 5. Maintainability & Technical Debt

### ✅ Achieved

- Module responsibilities are single and clearly documented at the top of each file.
- `Decimal` for monetary amounts throughout — no float rounding risk in financial figures.
- `from __future__ import annotations` uniformly applied — forward-compatible type hints.
- Test coverage is strong for a v0.1.0: 17 test files covering CLI, GUI, agent endpoints,
  streaming, corrections, routing, metadata, report, AI review, and documentation sync.
- Tests use `monkeypatch` to avoid heavy optional dependencies; the suite runs in CI on core
  deps only.

### ⚠️ Concerns

**`_call_ollama` Is Duplicated (Medium)** — see Section 4.

**`gui.py` Is Likely a God Module (Medium)**
The GUI entry point has ~10 distinct capabilities (progress bar, category editor, PDF export,
agent client integration, streaming dialog, corrections, undo) with no documented
sub-component decomposition.

**`RunOptions` Dynamic Attribute Mutation (Low)** — see Section 4.

**No Linter or Formatter Enforced in CI (Low)**
The CI workflow runs `pytest`, `compileall`, and `check_license_metadata.py` but does not run
`ruff`, `flake8`, `mypy`, or `black`. Code style inconsistencies will accumulate without a
gating linter.

**`python-docx` Declared but Unused (Low)**
`pyproject.toml:32` declares `python-docx` under the `docx` extra as "Planned". Installing the
extra installs a package that does nothing and can create false security audit findings.

### 💡 Recommendations

1. **Consolidate Ollama client** into `ollama_client.py` (see Section 4).
2. **Add `ruff` to CI:** `pip install ruff && ruff check src tests` — one step.
3. **Add `mypy` to CI (optional):** Would catch the `RunOptions` dynamic attribute issue.
4. **Remove `python-docx` from `[docx]` extra** until the feature is implemented.
5. **Decompose `gui.py`** into `gui_main.py`, `gui_workers.py`, `gui_dialogs.py`,
   `gui_export.py`.

---

## 6. Documentation

### ✅ Achieved

- `README.md` is comprehensive: installation, CLI options table, dry-run explanation, confidence
  score guide, known limitations, future improvements, license summary.
- `ARCHITECTURE.md` includes component diagram (ASCII), data flow narrative, module table,
  privacy/security section, and performance notes — rare quality for a v0.1.0.
- `CONTENT_PROVENANCE.md` clearly discloses AI-assisted development.
- `THIRD_PARTY_NOTICES.md` lists all direct dependencies with license and installation context,
  plus critical packaging notes for PySide6, Docling models, and Tesseract.
- `CHANGELOG.md` follows Keep a Changelog format with Semantic Versioning.
- `LICENSE_POLICY.md` documents redistribution obligations.
- Module docstrings are present and purposeful across all source files.

### ⚠️ Concerns

- **`ARCHITECTURE.md` does not reflect the duplicate Ollama client** — the diagram implies a
  cleaner abstraction than exists.
- **`gui.py` threading model is not documented** — which workers exist, which signals they emit,
  how agent server lifecycle ties to the GUI window.
- **`draw.io` file is not renderable in code review** — no PNG committed alongside the XML
  source, so diagrams are invisible in GitHub diffs.

### 💡 Recommendations

1. **Export drawio as PNG:** Add `docs/invoice_sorter_architecture.png` committed alongside the
   `.drawio` source. GitHub renders it inline in PR diffs.
2. **Document the threading model** in `ARCHITECTURE.md` — QThread workers, signals, and agent
   server start/stop lifecycle.
3. **Add a note** in the `ARCHITECTURE.md` "AI Integration" section acknowledging the two
   Ollama call implementations pending consolidation.

---

## 7. Twelve-Factor Compliance

| Factor | Status | Notes |
|---|---|---|
| I. Codebase | ✅ | Single repo, one deployable unit |
| II. Dependencies | ✅ | Fully declared in `pyproject.toml`; no implicit system deps beyond documented Tesseract |
| III. Config | ⚠️ | AI model names and agent port have code-level defaults; no env var for agent port |
| IV. Backing services | ✅ | Ollama treated as an attached service via URL |
| V. Build/release/run | ⚠️ | No PyPI publish workflow defined |
| VI. Processes | ✅ | Stateless pipeline; no module-level mutable state |
| VII. Port binding | ✅ | Agent server binds to configurable host:port |
| VIII. Concurrency | ❌ | Sequential single-process file loop; no horizontal scaling story |
| IX. Disposability | ✅ | Cooperative cancellation; partial outputs written on Stop/crash |
| X. Dev/prod parity | ✅ | Same code runs in dev and production (local-only tool) |
| XI. Logs | ⚠️ | Uses `print()` and `rich`; no `logging` module; errors only in `result.errors` strings |
| XII. Admin processes | ✅ | `scripts/suggest_local_config.py` is a proper one-off admin script |

### 💡 Recommendations

1. **Expose agent port via env var:** `INVOICE_SORTER_AGENT_PORT` — one-line change in
   `agent_service.py`.
2. **Replace `print()` with `logging`** in `agent_service.py` — minimum needed for log level
   control.
3. **Add a PyPI publish workflow** to `.github/workflows/` triggered on `v*` tags.

---

## Prioritised Findings Backlog

| Priority | Finding | Location | Effort |
|---|---|---|---|
| 🔴 P1-High | Prompt injection via extracted metadata | `ai_review.py:169`, `agent_service.py:162` | Small |
| 🔴 P1-High | `_call_ollama` duplicated across two modules | `ai_review.py`, `agent_service.py` | Small |
| 🟠 P2-Medium | Sequential processing loop — throughput ceiling | `orchestrator.py:123` | Medium |
| 🟠 P2-Medium | `requires-python = "==3.12.*"` blocks 3.13+ | `pyproject.toml:10` | Trivial |
| 🟠 P2-Medium | No input file size guard (OOM risk) | `scanner.py` | Small |
| 🟠 P2-Medium | Agent HTTP server has no authentication | `agent_service.py:441` | Small |
| 🟠 P2-Medium | All results buffered in RAM before output | `orchestrator.py:121` | Small |
| 🟡 P3-Low | `RunOptions` mutated with dynamic attributes | `orchestrator.py:129` | Small |
| 🟡 P3-Low | Fake streaming (buffer then chunk with sleep) | `agent_service.py:353` | Medium |
| 🟡 P3-Low | IBAN written verbatim to audit log | `audit_log.py:41` | Trivial |
| 🟡 P3-Low | No linter/formatter in CI | `.github/workflows/tests.yml` | Trivial |
| 🟡 P3-Low | `python-docx` declared but unused | `pyproject.toml:32` | Trivial |
| 🟡 P3-Low | Agent port 8080 not configurable via env var | `agent_service.py:31` | Trivial |
| 🟡 P3-Low | Full absolute path in audit log `source_file` | `audit_log.py:30` | Trivial |
| 🟡 P3-Low | `print()` instead of `logging` in agent service | `agent_service.py:454` | Small |
| 🟡 P3-Low | No rendered diagram in repo for PR review | `docs/invoice_sorter_architecture.drawio` | Trivial |

---

## Overall Assessment

**Invoice Sorter v0.1.0 is an architecturally sound, privacy-first personal tool.** The core
pipeline is clean, the separation of concerns is clear, testing is solid, and the documentation
is far above average for a first release. The identified issues are not design flaws — they are
the natural next maturity steps for a project moving from "personal prototype" to
"shared/distributable tool."

The highest-priority items (prompt injection sanitisation and Ollama client deduplication) are
low-effort changes that significantly improve correctness and maintainability and should be
addressed before the next release.
