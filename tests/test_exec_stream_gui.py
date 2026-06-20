"""Tests for ExecReportWorker streaming integration with GUI signals."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from invoice_sorter.gui import ExecReportWorker


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def test_exec_report_worker_emits_chunks_and_finishes(app, monkeypatch):
    # patch the streaming function used by the worker to yield predictable chunks
    def fake_stream(summary, options=None):
        yield "one"
        yield "two"
        yield "three"

    monkeypatch.setattr("invoice_sorter.gui.request_executive_report_stream", fake_stream)

    seen: list[str] = []
    finished = {"ok": False}

    worker = ExecReportWorker({"processed": 1}, options=None)
    worker.chunk_received.connect(lambda s: seen.append(s))
    worker.finished.connect(lambda: finished.update({"ok": True}))

    # run synchronously (avoid starting the thread) to keep test deterministic
    worker.run()

    assert seen == ["one", "two", "three"]
    assert finished["ok"] is True
