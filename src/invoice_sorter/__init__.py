"""Local-first invoice sorter for tax preparation.

Scans a folder of PDFs/images, extracts invoice metadata, classifies documents
into configurable categories with a transparent rule-based scorer, copies files
into category folders, and produces a Markdown report plus a JSONL audit log.

Privacy by design: no network access in the processing path, only extracted
metadata is persisted (never full invoice text), copy-mode by default, dry-run
available.
"""

__version__ = "0.1.0"
