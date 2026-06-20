"""Focused tests for GUI progress and cancellation controls."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QItemSelectionModel, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

from invoice_sorter.ai_review import (  # noqa: E402
    DEFAULT_ADVICE_MODEL,
    DEFAULT_CHAT_MODEL,
    DEFAULT_REPORT_MODEL,
)
from invoice_sorter.gui import MainWindow  # noqa: E402
from invoice_sorter.models import DocumentResult, ProcessingStatus  # noqa: E402
from invoice_sorter.report import RunSummary  # noqa: E402


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def test_progress_displays_completed_and_total_documents(app):
    window = MainWindow()

    assert window.ai_prompt_edit.text().endswith("config/ai_review_prompt.txt")
    assert window.ai_temperature.value() == 0.2
    assert window.advice_model_edit.text() == DEFAULT_ADVICE_MODEL
    assert window.report_model_edit.text() == DEFAULT_REPORT_MODEL
    assert window.chat_model_edit.text() == DEFAULT_CHAT_MODEL

    window._on_progress(3, 8)

    assert window.progress.minimum() == 0
    assert window.progress.maximum() == 8
    assert window.progress.value() == 3
    assert window.progress.format() == "3 / 8 documents"
    window.close()


def test_stop_button_requests_worker_cancellation(app):
    class WorkerStub:
        cancelled = False

        def cancel(self):
            self.cancelled = True

    window = MainWindow()
    worker = WorkerStub()
    window._worker = worker
    window.stop_btn.setEnabled(True)

    window._on_stop()

    assert worker.cancelled is True
    assert window.stop_btn.isEnabled() is False
    assert "Stopping" in window.summary_label.text()
    window.close()


def test_agent_server_starts_on_window_init(app, monkeypatch):
    class DummyHandle:
        def __init__(self):
            self.shutdown_called = False

        def shutdown(self):
            self.shutdown_called = True

    dummy_handle = DummyHandle()
    started = {}

    def fake_start_agent_server(host, port):
        started["host"] = host
        started["port"] = port
        return dummy_handle

    monkeypatch.setattr("invoice_sorter.gui.start_agent_server", fake_start_agent_server)

    window = MainWindow()

    assert window._agent_handle is dummy_handle
    assert started["host"] == "127.0.0.1"
    assert started["port"] == 8080
    assert window.agent_status_label.text() == "Agent server: http://127.0.0.1:8080"

    window.close()
    assert dummy_handle.shutdown_called is True


def test_manual_review_rows_use_red_background_and_white_text(app):
    window = MainWindow()
    result = DocumentResult(source_path=Path("anonymous.pdf"))
    result.category = "Unklar / Manuell prüfen"
    result.status = ProcessingStatus.MANUAL_REVIEW

    window._on_finished([result], RunSummary(total_scanned=1))

    item = window.table.item(0, 0)
    assert item.background().color().getRgb()[:3] == (185, 28, 28)
    assert item.foreground().color().getRgb()[:3] == (255, 255, 255)
    window.close()


def test_batch_category_edit_tracks_results_after_sorting(app, monkeypatch):
    window = MainWindow()
    results = [
        DocumentResult(source_path=Path("z.pdf"), category="Internet"),
        DocumentResult(source_path=Path("a.pdf"), category="Arbeit"),
        DocumentResult(source_path=Path("m.pdf"), category="Musik"),
    ]
    window._on_finished(results, RunSummary(total_scanned=3))
    window.table.sortItems(0, Qt.AscendingOrder)

    selection = window.table.selectionModel()
    for row in (0, 2):
        selection.select(
            window.table.model().index(row, 0),
            QItemSelectionModel.Select | QItemSelectionModel.Rows,
        )
    monkeypatch.setattr(QInputDialog, "getItem", lambda *_args, **_kwargs: ("Steuern", True))

    window._edit_category()

    assert results[0].category == "Steuern"
    assert results[1].category == "Steuern"
    assert results[2].category == "Musik"
    assert len(window._correction_log.changes) == 2
    window.close()


def test_undo_uses_stable_result_index_after_sorting(app, monkeypatch):
    window = MainWindow()
    results = [
        DocumentResult(source_path=Path("z.pdf"), category="Internet"),
        DocumentResult(source_path=Path("a.pdf"), category="Arbeit"),
    ]
    window._on_finished(results, RunSummary(total_scanned=2))
    window.table.sortItems(0, Qt.AscendingOrder)
    monkeypatch.setattr(QInputDialog, "getItem", lambda *_args, **_kwargs: ("Steuern", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)

    window._edit_category_rows([0])
    window.table.sortItems(0, Qt.DescendingOrder)
    window._undo_last_change()

    assert results[0].category == "Internet"
    assert results[1].category == "Arbeit"
    window.close()
