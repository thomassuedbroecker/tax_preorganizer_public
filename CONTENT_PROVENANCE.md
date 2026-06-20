# Content Provenance

## Development Provenance

This repository has been developed with human direction and review and with
assistance from GitHub Copilot, OpenAI Codex, Claude Code, and IBM Bob. The
project owner selected requirements, reviewed changes, ran tests, and accepted
the resulting implementation.

Development prompts and interaction logs are intentionally excluded from the
public repository. Runtime prompt templates are stored under `config/`.

## Review Expectations

AI-assisted content is treated like any other contribution:

- It must be reviewed for correctness, privacy, security, and maintainability.
- It must not knowingly reproduce third-party code without preserving applicable
  license obligations.
- Tests and repository review provide evidence of human selection and validation,
  but do not by themselves prove absence of public-code similarity.
- Contributors should disclose substantial generated content when that context is
  useful for review or provenance.

## Runtime AI

The optional Ollama integration has two components:

1. **Post-sort review** (`ai_review.py`): After deterministic sorting completes,
   generates a review of the aggregate category distribution and metadata. Does
   not classify or change file placement. Only extracted metadata (counts, vendor
   names, dates, amounts) — never full invoice text — is sent to the local Ollama
   instance.

2. **Agent REST service**: `agent_service.py` runs a LangGraph/Ollama service
   locally on `127.0.0.1:8080`. It exposes:
   - `GET /api/health`: Reports local service readiness.
   - `/api/document-advice`: Accepts a single document result, returns AI-generated
     advice on the classification decision.
   - `/api/document-chat`: Answers a chat turn from one document's metadata,
     optional history, and configured category names.
   - `/api/executive-report`: Returns a synchronous executive report.
   - `/api/executive-report-stream`: Accepts a run summary, streams back an
     executive report as newline-delimited JSON chunks (real-time display in GUI).

   The agent wraps Ollama for inference. Full invoice text is never sent; only
   extracted metadata fields (vendor, category, confidence, etc.) are provided.
   Separate model defaults are used for reasoning-oriented review/advice,
   longer executive synthesis, and latency-sensitive chat. All defaults can be
   overridden through environment variables or GUI fields.

## External Artifacts

No model weights, training datasets, or third-party source trees are committed to
this repository. Optional extraction/model downloads remain subject to their own
terms and provenance requirements.

This record is provided for transparency and is not a legal determination of
copyright ownership or license compatibility.
