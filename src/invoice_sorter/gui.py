"""PySide6 desktop UI for the invoice sorter.

A thin window on top of :func:`invoice_sorter.orchestrator.run`. The heavy work
runs in a worker thread so the window stays responsive (Docling can be slow).

Privacy: this is a local desktop app showing your own data on your own machine.
Dry-run is ON by default so the first click never copies anything.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from threading import Event
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QPageLayout,
    QTextDocument,
    QTextCursor,
)
from PySide6.QtPrintSupport import QPrinter
import csv
import time
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QDialog,
    QTextEdit,
    QFormLayout,
    QDialogButtonBox,
)

from .ai_review import (
    DEFAULT_ADVICE_MODEL,
    DEFAULT_CHAT_MODEL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    DEFAULT_REPORT_MODEL,
)
from .agent_client import (
    AgentClientOptions,
    request_document_advice,
    request_document_chat,
    request_executive_report,
    request_executive_report_stream,
)
from .corrections import apply_document_edits
from .agent_service import DEFAULT_AGENT_HOST, DEFAULT_AGENT_PORT, AgentServerHandle, start_agent_server
from .config import ConfigError, load_config
from .extraction_adapter import active_backend
from .models import UNKNOWN, ProcessingStatus
from .orchestrator import RunOptions, run
from .report import REPORT_NAME

_DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "categories.yaml"
_DEFAULT_AI_PROMPT = Path(__file__).resolve().parents[2] / "config" / "ai_review_prompt.txt"

_COLUMNS = ["File", "Category", "Vendor", "Invoice Date", "Gross", "Currency",
            "Confidence", "Status", "Notes"]
_RESULT_INDEX_ROLE = Qt.UserRole + 1


def _cell(value) -> str:
    if value is None:
        return UNKNOWN
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _format_elapsed(seconds: int) -> str:
    """Format seconds as H:MM:SS or M:SS."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class CorrectionLog:
    """Track category changes for undo and export."""

    def __init__(self) -> None:
        # The first value is the stable index in ``_last_results``, not the
        # current visible table row (which changes whenever the user sorts).
        self.changes: list[tuple[int, str, str]] = []

    def add_change(self, result_index: int, old_cat: str, new_cat: str) -> None:
        self.changes.append((result_index, old_cat, new_cat))

    def undo_last(self) -> tuple[int, str, str] | None:
        return self.changes.pop() if self.changes else None

    def clear(self) -> None:
        self.changes.clear()

    def as_csv(self) -> str:
        lines = ["row,old_category,new_category"]
        for row, old_cat, new_cat in self.changes:
            lines.append(f"{row},{old_cat},{new_cat}")
        return "\n".join(lines)


class Worker(QObject):
    """Runs the pipeline off the UI thread."""

    finished = Signal(object, object)  # (results, summary)
    failed = Signal(str)
    progress = Signal(int, int)  # (completed, total)

    def __init__(self, options: RunOptions) -> None:
        super().__init__()
        self.options = options
        self._cancel_requested = Event()
        self.options.progress_callback = self.progress.emit
        self.options.cancel_check = self._cancel_requested.is_set

    def cancel(self) -> None:
        self._cancel_requested.set()

    def run(self) -> None:
        try:
            results, summary = run(self.options)
            self.finished.emit(results, summary)
        except Exception as exc:  # surfaced in a dialog, never crashes the app
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class ExecReportWorker(QThread):
    chunk_received = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, summary: dict[str, Any], options: AgentClientOptions | None = None) -> None:
        super().__init__()
        self._summary = summary
        self._options = options or AgentClientOptions()
        self._stopped = False

    def run(self) -> None:
        try:
            for chunk in request_executive_report_stream(self._summary, options=self._options):
                if self._stopped:
                    break
                self.chunk_received.emit(chunk)
            self.finished.emit()
        except Exception as exc:
            self.error.emit(str(exc))

    def stop(self) -> None:
        self._stopped = True


class ChatWorker(QThread):
    """Runs one document-chat turn off the UI thread (Ollama can be slow)."""

    reply = Signal(str)
    failed = Signal(str)

    def __init__(self, document, message, history, categories, options) -> None:
        super().__init__()
        self._document = document
        self._message = message
        self._history = history
        self._categories = categories
        self._options = options

    def run(self) -> None:
        try:
            text = request_document_chat(
                self._document,
                self._message,
                history=self._history,
                categories=self._categories,
                options=self._options,
            )
            self.reply.emit(text)
        except Exception as exc:  # surfaced in the dialog
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Invoice Sorter")
        self.resize(1040, 640)
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self._last_output: Path | None = None
        self._run_start: float | None = None
        self._agent_handle: AgentServerHandle | None = None
        self._exec_worker: ExecReportWorker | None = None
        self._correction_log: CorrectionLog = CorrectionLog()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # --- form -------------------------------------------------------
        form = QGridLayout()
        self.input_edit = QLineEdit()
        self.output_edit = QLineEdit()
        self.config_edit = QLineEdit(str(_DEFAULT_CONFIG))
        form.addWidget(QLabel("Input folder"), 0, 0)
        form.addWidget(self.input_edit, 0, 1)
        form.addWidget(self._browse_btn(self.input_edit, folder=True), 0, 2)
        form.addWidget(QLabel("Output folder"), 1, 0)
        form.addWidget(self.output_edit, 1, 1)
        form.addWidget(self._browse_btn(self.output_edit, folder=True), 1, 2)
        form.addWidget(QLabel("Config (categories.yaml)"), 2, 0)
        form.addWidget(self.config_edit, 2, 1)
        form.addWidget(self._browse_btn(self.config_edit, folder=False), 2, 2)
        self.ai_model_edit = QLineEdit(DEFAULT_OLLAMA_MODEL)
        self.ai_url_edit = QLineEdit(DEFAULT_OLLAMA_URL)
        self.ai_prompt_edit = QLineEdit(str(_DEFAULT_AI_PROMPT))
        self.ai_temperature = QDoubleSpinBox()
        self.ai_temperature.setRange(0.0, 2.0)
        self.ai_temperature.setDecimals(2)
        self.ai_temperature.setSingleStep(0.1)
        self.ai_temperature.setValue(0.2)
        form.addWidget(QLabel("AI review model"), 3, 0)
        form.addWidget(self.ai_model_edit, 3, 1)
        form.addWidget(QLabel("Ollama URL"), 4, 0)
        form.addWidget(self.ai_url_edit, 4, 1)
        form.addWidget(QLabel("AI temperature"), 5, 0)
        form.addWidget(self.ai_temperature, 5, 1)
        form.addWidget(QLabel("AI review prompt"), 6, 0)
        form.addWidget(self.ai_prompt_edit, 6, 1)
        form.addWidget(
            self._browse_btn(
                self.ai_prompt_edit,
                folder=False,
                file_filter="Prompt templates (*.txt *.md);;All files (*)",
            ),
            6,
            2,
        )
        self.agent_host_edit = QLineEdit("127.0.0.1")
        self.agent_port_edit = QLineEdit("8080")
        form.addWidget(QLabel("Agent host"), 7, 0)
        form.addWidget(self.agent_host_edit, 7, 1)
        form.addWidget(QLabel("Agent port"), 8, 0)
        form.addWidget(self.agent_port_edit, 8, 1)
        root.addLayout(form)

        # Per-feature agent models (each can use a different Ollama model).
        self.advice_model_edit = QLineEdit(DEFAULT_ADVICE_MODEL)
        self.report_model_edit = QLineEdit(DEFAULT_REPORT_MODEL)
        self.chat_model_edit = QLineEdit(DEFAULT_CHAT_MODEL)
        agent_models_row = QHBoxLayout()
        agent_models_row.addWidget(QLabel("Agent models —  Advice:"))
        agent_models_row.addWidget(self.advice_model_edit)
        agent_models_row.addWidget(QLabel("Exec Report:"))
        agent_models_row.addWidget(self.report_model_edit)
        agent_models_row.addWidget(QLabel("Chat:"))
        agent_models_row.addWidget(self.chat_model_edit)
        root.addLayout(agent_models_row)

        # --- options ----------------------------------------------------
        opts = QHBoxLayout()
        self.dry_run = QCheckBox("Dry run (no files copied)")
        self.dry_run.setChecked(True)
        self.recursive = QCheckBox("Recursive")
        self.recursive.setChecked(True)
        self.move = QCheckBox("Move instead of copy")
        self.ai_review = QCheckBox("Local AI review")
        self.backend_combo = QComboBox()
        self.backend_combo.addItem(f"Auto ({active_backend()})", "auto")
        self.backend_combo.addItem("Docling", "docling")
        self.backend_combo.addItem("Light", "light")
        opts.addWidget(self.dry_run)
        opts.addWidget(self.recursive)
        opts.addWidget(self.move)
        opts.addWidget(self.ai_review)
        opts.addStretch(1)
        opts.addWidget(QLabel("Backend"))
        opts.addWidget(self.backend_combo)
        root.addLayout(opts)

        # --- run row ----------------------------------------------------
        run_row = QHBoxLayout()
        self.run_btn = QPushButton("Run")
        self.run_btn.clicked.connect(self._on_run)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        self.open_report_btn = QPushButton("Open report")
        self.open_report_btn.clicked.connect(self._open_report)
        self.open_report_btn.setEnabled(False)
        self.open_folder_btn = QPushButton("Open output folder")
        self.open_folder_btn.clicked.connect(self._open_folder)
        self.open_folder_btn.setEnabled(False)
        self.export_csv_btn = QPushButton("Export CSV")
        self.export_csv_btn.clicked.connect(self._export_table_csv)
        self.export_csv_btn.setEnabled(False)
        self.exec_pdf_btn = QPushButton("Generate Exec PDF")
        self.exec_pdf_btn.clicked.connect(self._generate_exec_pdf)
        self.exec_pdf_btn.setEnabled(False)
        self.agent_advice_btn = QPushButton("Document Advice")
        self.agent_advice_btn.clicked.connect(self._request_document_advice)
        self.agent_advice_btn.setEnabled(False)
        self.agent_report_btn = QPushButton("Agent Exec Report")
        self.agent_report_btn.clicked.connect(self._request_executive_report)
        self.agent_report_btn.setEnabled(False)
        self.chat_btn = QPushButton("Chat / Edit")
        self.chat_btn.clicked.connect(self._chat_about_document)
        self.chat_btn.setEnabled(False)
        self.edit_category_btn = QPushButton("Edit Category")
        self.edit_category_btn.clicked.connect(self._edit_category)
        self.edit_category_btn.setEnabled(False)
        self.undo_btn = QPushButton("Undo Last Change")
        self.undo_btn.clicked.connect(self._undo_last_change)
        self.undo_btn.setEnabled(False)
        self.export_corrections_btn = QPushButton("Export Corrections")
        self.export_corrections_btn.clicked.connect(self._export_corrections)
        self.export_corrections_btn.setEnabled(False)
        self.agent_status_label = QLabel("Agent server: stopped")
        run_row.addWidget(self.run_btn)
        run_row.addWidget(self.stop_btn)
        run_row.addWidget(self.open_report_btn)
        run_row.addWidget(self.export_csv_btn)
        run_row.addWidget(self.exec_pdf_btn)
        run_row.addWidget(self.agent_advice_btn)
        run_row.addWidget(self.agent_report_btn)
        run_row.addWidget(self.chat_btn)
        run_row.addWidget(self.edit_category_btn)
        run_row.addWidget(self.undo_btn)
        run_row.addWidget(self.export_corrections_btn)
        run_row.addWidget(self.open_folder_btn)
        run_row.addWidget(self.agent_status_label)
        run_row.addStretch(1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setMinimumWidth(180)
        self.progress.hide()
        run_row.addWidget(self.progress)
        root.addLayout(run_row)

        # --- summary ----------------------------------------------------
        self.summary_label = QLabel("Pick an input folder and click Run.")
        root.addWidget(self.summary_label)

        # --- table ------------------------------------------------------
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(self._open_selected_file)
        root.addWidget(self.table, 1)

        self._start_agent_server()

    # --- helpers --------------------------------------------------------
    def _browse_btn(
        self,
        target: QLineEdit,
        *,
        folder: bool,
        file_filter: str = "YAML/JSON (*.yaml *.yml *.json)",
    ) -> QPushButton:
        btn = QPushButton("Browse…")

        def choose() -> None:
            if folder:
                path = QFileDialog.getExistingDirectory(self, "Select folder")
            else:
                path, _ = QFileDialog.getOpenFileName(
                    self, "Select file", "", file_filter
                )
            if path:
                target.setText(path)

        btn.clicked.connect(choose)
        return btn

    def _set_busy(self, busy: bool) -> None:
        self.run_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        if busy:
            self.progress.setRange(0, 0)
            self.progress.setFormat("Preparing documents…")
        self.progress.setVisible(busy)

    def _start_agent_server(self) -> None:
        if self._agent_handle is not None:
            return
        host = self.agent_host_edit.text().strip() or DEFAULT_AGENT_HOST
        port = int(self.agent_port_edit.text().strip() or str(DEFAULT_AGENT_PORT))
        try:
            self._agent_handle = start_agent_server(host=host, port=port)
            self.agent_status_label.setText(f"Agent server: http://{host}:{port}")
        except OSError as exc:
            # Do NOT show a modal here: a modal on startup blocks headless/test
            # runs forever (no one to click OK) and is poor UX. Report inline.
            self.agent_status_label.setText(f"Agent server: not started ({exc})")
            self._agent_handle = None

    def _stop_agent_server(self) -> None:
        if self._agent_handle is None:
            return
        try:
            self._agent_handle.shutdown()
        except Exception:
            pass
        self._agent_handle = None
        self.agent_status_label.setText("Agent server: stopped")

    def closeEvent(self, event) -> None:
        self._stop_agent_server()
        event.accept()

    def _on_progress(self, completed: int, total: int) -> None:
        maximum = max(total, 1)
        self.progress.setRange(0, maximum)
        self.progress.setValue(completed if total else maximum)
        self.progress.setFormat(f"{completed} / {total} documents")
        # Show live processed and remaining counts in the summary label.
        remaining = max(total - completed, 0)
        # include elapsed time if available
        elapsed_text = ""
        if getattr(self, "_run_start", None):
            elapsed = int(time.time() - self._run_start)
            elapsed_text = f" · elapsed { _format_elapsed(elapsed) }"

        # percent and ETA
        percent_text = ""
        eta_text = ""
        if total:
            pct = int(round((completed / total) * 100))
            percent_text = f" · {pct}%"
            if completed > 0 and getattr(self, "_run_start", None):
                avg = (time.time() - self._run_start) / completed
                remaining_secs = int(avg * max(total - completed, 0))
                eta_text = f" · ETA { _format_elapsed(remaining_secs) }"

        # current filename and unit/token info (if provided by orchestrator)
        current_file = ""
        tokens_text = ""
        if self._worker and getattr(self._worker, "options", None):
            opts = self._worker.options
            fname = getattr(opts, "latest_filename", None)
            units = getattr(opts, "latest_unit_count", None)
            if fname:
                current_file = f" · file {fname}"
            if getattr(self, "_last_summary", None) and self._last_summary.ai_review_metrics:
                tokens = self._last_summary.ai_review_metrics.get("total_tokens")
                tokens_text = f" · tokens {tokens}"
            elif units is not None:
                tokens_text = f" · units {units}"

        self.summary_label.setText(
            f"Working… processed {completed} · remaining {remaining} · total {total}{percent_text}{eta_text}{elapsed_text}{current_file}{tokens_text}"
        )

    def _on_stop(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        self.stop_btn.setEnabled(False)
        self.summary_label.setText("Stopping after the current document…")

    # --- actions --------------------------------------------------------
    def _on_run(self) -> None:
        input_dir = Path(self.input_edit.text().strip()).expanduser()
        output_dir = Path(self.output_edit.text().strip()).expanduser()

        if not input_dir.is_dir():
            QMessageBox.warning(self, "Invalid input", "Input folder does not exist.")
            return
        if not output_dir.name:
            QMessageBox.warning(self, "Missing output", "Choose an output folder.")
            return
        try:
            config = load_config(self.config_edit.text().strip() or str(_DEFAULT_CONFIG))
        except ConfigError as exc:
            QMessageBox.critical(self, "Config error", str(exc))
            return

        options = RunOptions(
            input_dir=input_dir,
            output_dir=output_dir,
            config=config,
            dry_run=self.dry_run.isChecked(),
            recursive=self.recursive.isChecked(),
            move=self.move.isChecked(),
            extraction_backend=self.backend_combo.currentData(),
            ai_review=self.ai_review.isChecked(),
            ai_model=self.ai_model_edit.text().strip() or DEFAULT_OLLAMA_MODEL,
            ai_base_url=self.ai_url_edit.text().strip() or DEFAULT_OLLAMA_URL,
            ai_prompt_path=(
                Path(self.ai_prompt_edit.text().strip()).expanduser()
                if self.ai_prompt_edit.text().strip()
                else None
            ),
            ai_temperature=self.ai_temperature.value(),
        )
        self._last_output = output_dir

        # record start time for elapsed display
        self._run_start = time.time()

        self._set_busy(True)
        self.summary_label.setText("Working… (Docling can take a while on first run)")

        self._thread = QThread()
        self._worker = Worker(options)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Run failed", message)
        self.summary_label.setText("Run failed.")

    def _on_finished(self, results, summary) -> None:
        self._set_busy(False)
        self.open_report_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(True)
        self.export_csv_btn.setEnabled(True)
        self.exec_pdf_btn.setEnabled(True)
        self.agent_advice_btn.setEnabled(True)
        self.agent_report_btn.setEnabled(True)
        self.chat_btn.setEnabled(True)
        self.edit_category_btn.setEnabled(True)
        self.export_corrections_btn.setEnabled(True)
        self._correction_log.clear()
        # Save for later export actions
        self._last_results = results
        self._last_summary = summary

        manual = sum(1 for r in results
                     if r.status == ProcessingStatus.MANUAL_REVIEW
                     or r.category == summary.manual_review_category)
        failed = sum(1 for r in results if r.status == ProcessingStatus.FAILED)
        mode = "DRY RUN" if summary.dry_run else ("MOVE" if self.move.isChecked() else "COPY")
        if summary.cancelled:
            mode = f"CANCELLED {mode}"
        self.summary_label.setText(
            f"<b>{mode}</b> · scanned {summary.total_scanned} · processed "
            f"{len(results)} · sorted {len(results) - manual - failed} · "
            f"review {manual} · failed {failed} · unsupported "
            f"{len(summary.unsupported_files)}"
        )

        # final elapsed display
        if getattr(self, "_run_start", None):
            elapsed = int(time.time() - self._run_start)
            # append elapsed to the summary label
            self.summary_label.setText(self.summary_label.text() + f" · elapsed { _format_elapsed(elapsed) }")
            self._run_start = None

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(results))
        for row, r in enumerate(results):
            m = r.metadata
            values = [
                r.source_path.name, r.category, _cell(m.vendor), _cell(m.invoice_date),
                _cell(m.gross_amount), _cell(m.currency), f"{r.confidence:.2f}",
                r.status.value, "; ".join(r.notes),
            ]
            is_manual = (r.status == ProcessingStatus.MANUAL_REVIEW
                         or r.category == summary.manual_review_category)
            is_failed = r.status == ProcessingStatus.FAILED
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setData(Qt.UserRole, str(r.source_path))
                    item.setData(_RESULT_INDEX_ROLE, row)
                if is_failed:
                    item.setBackground(QColor(255, 224, 224))
                elif is_manual:
                    item.setBackground(QColor(185, 28, 28))
                    item.setForeground(QColor(255, 255, 255))
                # Confidence column (col 6): exact 1.0 -> strong green + white text,
                # high confidence >= 0.9 -> pale green with dark text.
                elif col == 6 and r.confidence >= 0.9999:
                    item.setBackground(QColor(0, 128, 0))
                    item.setForeground(QColor(255, 255, 255))
                elif col == 6 and r.confidence >= 0.9:
                    item.setBackground(QColor(184, 255, 184))
                    item.setForeground(QColor(0, 0, 0))
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)

    def _generate_exec_pdf(self) -> None:
        if not getattr(self, "_last_results", None) or not getattr(self, "_last_summary", None):
            QMessageBox.warning(self, "No data", "Run the sorter first to generate a report.")
            return
        default_path = str(self._last_output / "invoice_summary_exec.pdf") if self._last_output else ""
        path, _ = QFileDialog.getSaveFileName(self, "Save executive PDF", default_path, "PDF files (*.pdf);;All files (*)")
        if not path:
            return
        try:
            from .report import build_report

            md = build_report(self._last_results, self._last_summary, compact_table=True)
            render_markdown_to_pdf(md, path)
            QMessageBox.information(self, "PDF saved", f"Executive PDF written to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "PDF generation failed", str(exc))

    def _open_report(self) -> None:
        if self._last_output:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self._last_output / REPORT_NAME))
            )

    def _open_folder(self) -> None:
        if self._last_output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output)))

    def _open_selected_file(self, row: int, column: int) -> None:
        # If user double-clicked the Category column, allow editing the category.
        if column == 1:
            self._edit_category_rows([row])
            return

        # otherwise open the source file for other columns (default behavior)
        if not getattr(self, "_last_results", None):
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        source_path = item.data(Qt.UserRole)
        if not source_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(source_path)))
    def _result_index_for_row(self, row: int) -> int | None:
        item = self.table.item(row, 0)
        if item is None:
            return None
        value = item.data(_RESULT_INDEX_ROLE)
        return int(value) if value is not None else None

    def _table_row_for_result(self, result_index: int) -> int | None:
        for row in range(self.table.rowCount()):
            if self._result_index_for_row(row) == result_index:
                return row
        return None

    def _edit_category_rows(self, rows: list[int]) -> None:
        if not rows:
            return
        try:
            cfg = load_config(self.config_edit.text().strip() or str(_DEFAULT_CONFIG))
            categories = cfg.category_names()
        except Exception:
            categories = []

        current_values = {
            self.table.item(row, 1).text()
            for row in rows
            if self.table.item(row, 1) is not None
        }
        current = next(iter(current_values)) if len(current_values) == 1 else ""
        if categories:
            current_index = categories.index(current) if current in categories else 0
            choice, ok = QInputDialog.getItem(
                self,
                "Select category",
                f"Category for {len(rows)} selected document(s):",
                categories,
                current_index,
                False,
            )
        else:
            choice, ok = QInputDialog.getText(
                self,
                "Edit category",
                f"Category for {len(rows)} selected document(s):",
                text=current,
            )
        if not ok or not choice:
            return

        changed = False
        sorting_enabled = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        try:
            for row in rows:
                item = self.table.item(row, 1)
                old_category = item.text() if item is not None else ""
                result_index = self._result_index_for_row(row)
                if old_category == choice or result_index is None:
                    continue
                self._correction_log.add_change(result_index, old_category, choice)
                if item is None:
                    item = QTableWidgetItem(choice)
                    self.table.setItem(row, 1, item)
                else:
                    item.setText(choice)
                if result_index < len(self._last_results):
                    self._last_results[result_index].category = choice
                changed = True
        finally:
            self.table.setSortingEnabled(sorting_enabled)
        if changed:
            self.undo_btn.setEnabled(True)

    def _edit_category(self) -> None:
        """Apply one category to all selected document rows."""
        if not getattr(self, "_last_results", None):
            QMessageBox.warning(self, "No data", "Run the sorter first to edit categories.")
            return
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            QMessageBox.warning(self, "Select rows", "Select one or more rows first.")
            return
        self._edit_category_rows(rows)

    def _undo_last_change(self) -> None:
        """Undo the last category change."""
        undo_result = self._correction_log.undo_last()
        if not undo_result:
            QMessageBox.information(self, "Undo", "No changes to undo.")
            return
        result_index, old_cat, new_cat = undo_result
        row = self._table_row_for_result(result_index)
        if row is None:
            QMessageBox.warning(self, "Undo", "The edited document is no longer in the table.")
            return
        current_item = self.table.item(row, 1)
        if current_item is not None:
            current_item.setText(old_cat)
        if getattr(self, "_last_results", None) and result_index < len(self._last_results):
            self._last_results[result_index].category = old_cat
        if not self._correction_log.changes:
            self.undo_btn.setEnabled(False)
        QMessageBox.information(self, "Undo", f"Reverted row {row}: {new_cat} → {old_cat}")

    def _export_corrections(self) -> None:
        """Export the correction log as CSV."""
        if not self._correction_log.changes:
            QMessageBox.information(self, "Corrections", "No category changes to export.")
            return
        default_path = (
            str(self._last_output / "category_corrections.csv") if self._last_output else ""
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export corrections", default_path, "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        try:
            content = self._correction_log.as_csv()
            Path(path).write_text(content, encoding="utf-8")
            QMessageBox.information(self, "Export complete", f"Wrote corrections to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
    def _request_document_advice(self) -> None:
        if not getattr(self, "_last_results", None):
            QMessageBox.warning(self, "No data", "Run the sorter first to request advice.")
            return
        if not getattr(self, "_last_summary", None):
            QMessageBox.warning(self, "No data", "Run the sorter first to request advice.")
            return
        try:
            host = self.agent_host_edit.text().strip() or "127.0.0.1"
            port = int(self.agent_port_edit.text().strip() or "8080")
            options = AgentClientOptions(
                base_url=f"http://{host}:{port}",
                model=self.advice_model_edit.text().strip() or None,
                temperature=float(self.ai_temperature.value()),
            )
            row = self.table.currentRow()
            if row < 0:
                QMessageBox.warning(self, "Select row", "Select one document row first.")
                return
            document = {
                "file_name": self.table.item(row, 0).text(),
                "category": self.table.item(row, 1).text(),
                "vendor": self.table.item(row, 2).text(),
                "invoice_date": self.table.item(row, 3).text(),
                "gross": self.table.item(row, 4).text(),
                "currency": self.table.item(row, 5).text(),
                "confidence": float(self.table.item(row, 6).text()),
                "status": self.table.item(row, 7).text(),
                "notes": self.table.item(row, 8).text(),
            }
            advice = request_document_advice(document, options)
            QMessageBox.information(self, "Document Advice", advice)
        except Exception as exc:
            QMessageBox.critical(self, "Agent request failed", str(exc))

    def _doc_payload(self, result) -> dict:
        m = result.metadata
        def s(v):
            return str(v) if v is not None else None
        return {
            "file_name": result.source_path.name,
            "category": result.category,
            "confidence": result.confidence,
            "status": result.status.value,
            "notes": result.notes,
            "vendor": m.vendor,
            "invoice_date": m.invoice_date,
            "invoice_number": m.invoice_number,
            "gross_amount": s(m.gross_amount),
            "vat_amount": s(m.vat_amount),
            "net_amount": s(m.net_amount),
            "currency": m.currency,
        }

    def _set_row_from_result(self, row: int, r) -> None:
        m = r.metadata
        values = [
            r.source_path.name, r.category, _cell(m.vendor), _cell(m.invoice_date),
            _cell(m.gross_amount), _cell(m.currency), f"{r.confidence:.2f}",
            r.status.value, "; ".join(r.notes),
        ]
        for col, val in enumerate(values):
            item = self.table.item(row, col)
            if item is None:
                item = QTableWidgetItem(val)
                self.table.setItem(row, col, item)
            else:
                item.setText(val)
        first = self.table.item(row, 0)
        if first is not None:
            first.setData(Qt.UserRole, str(r.source_path))

    def _chat_about_document(self) -> None:
        """Chat with the local agent about the selected document and edit its
        category/metadata."""
        if not getattr(self, "_last_results", None):
            QMessageBox.warning(self, "No data", "Run the sorter first.")
            return
        row = self.table.currentRow()
        result_index = self._result_index_for_row(row) if row >= 0 else None
        if result_index is None or result_index >= len(self._last_results):
            QMessageBox.warning(self, "Select row", "Select one document row first.")
            return
        result = self._last_results[result_index]

        try:
            cfg = load_config(self.config_edit.text().strip() or str(_DEFAULT_CONFIG))
            categories = cfg.category_names()
        except Exception:
            categories = []

        host = self.agent_host_edit.text().strip() or "127.0.0.1"
        port = int(self.agent_port_edit.text().strip() or "8080")
        options = AgentClientOptions(
            base_url=f"http://{host}:{port}",
            model=self.chat_model_edit.text().strip() or None,
            temperature=float(self.ai_temperature.value()),
        )

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Chat / Edit — {result.source_path.name}")
        dialog.resize(620, 620)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            f"<b>{result.source_path.name}</b> · {result.category} · "
            f"confidence {result.confidence:.2f}"
        ))

        transcript = QTextEdit(dialog)
        transcript.setReadOnly(True)
        layout.addWidget(transcript, 1)

        chat_row = QHBoxLayout()
        chat_input = QLineEdit(dialog)
        chat_input.setPlaceholderText("Ask the agent about this document…")
        send_btn = QPushButton("Send", dialog)
        chat_row.addWidget(chat_input, 1)
        chat_row.addWidget(send_btn)
        layout.addLayout(chat_row)

        # --- editable category + metadata ---
        form = QFormLayout()
        cat_combo = QComboBox(dialog)
        cat_combo.setEditable(True)
        if categories:
            cat_combo.addItems(categories)
        cur = result.category
        if cur and categories and cur in categories:
            cat_combo.setCurrentIndex(categories.index(cur))
        else:
            cat_combo.setEditText(cur or "")
        form.addRow("Category", cat_combo)

        m = result.metadata
        def field(value) -> QLineEdit:
            return QLineEdit("" if value is None else str(value), dialog)
        edits_widgets = {
            "vendor": field(m.vendor),
            "invoice_date": field(m.invoice_date),
            "invoice_number": field(m.invoice_number),
            "gross_amount": field(m.gross_amount),
            "vat_amount": field(m.vat_amount),
            "net_amount": field(m.net_amount),
            "currency": field(m.currency),
        }
        for label, widget in edits_widgets.items():
            form.addRow(label.replace("_", " ").title(), widget)
        layout.addLayout(form)

        buttons = QDialogButtonBox(dialog)
        apply_btn = buttons.addButton("Apply changes", QDialogButtonBox.AcceptRole)
        close_btn = buttons.addButton(QDialogButtonBox.Close)
        layout.addWidget(buttons)

        history: list[dict[str, str]] = []

        def on_send() -> None:
            message = chat_input.text().strip()
            if not message:
                return
            transcript.append(f"<b>You:</b> {message}")
            chat_input.clear()
            send_btn.setEnabled(False)
            worker = ChatWorker(self._doc_payload(result), message, list(history), categories, options)
            self._chat_worker = worker

            def on_reply(text: str) -> None:
                transcript.append(f"<b>Agent:</b> {text}")
                history.append({"role": "user", "content": message})
                history.append({"role": "assistant", "content": text})
                send_btn.setEnabled(True)

            def on_fail(err: str) -> None:
                transcript.append(f"<i>Agent error: {err}</i>")
                send_btn.setEnabled(True)

            worker.reply.connect(on_reply)
            worker.failed.connect(on_fail)
            worker.start()

        def on_apply() -> None:
            old_category = result.category
            edits: dict[str, str] = {"category": cat_combo.currentText().strip()}
            for key, widget in edits_widgets.items():
                edits[key] = widget.text()
            changes = apply_document_edits(result, edits)
            if not changes:
                QMessageBox.information(dialog, "No changes", "Nothing to apply.")
                return
            if result.category != old_category:
                self._correction_log.add_change(result_index, old_category, result.category)
                self.undo_btn.setEnabled(True)
            self._set_row_from_result(row, result)
            QMessageBox.information(dialog, "Applied", "Updated:\n- " + "\n- ".join(changes))

        send_btn.clicked.connect(on_send)
        chat_input.returnPressed.connect(on_send)
        apply_btn.clicked.connect(on_apply)
        close_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def _request_executive_report(self) -> None:
        if not getattr(self, "_last_results", None) or not getattr(self, "_last_summary", None):
            QMessageBox.warning(self, "No data", "Run the sorter first to request an executive report.")
            return
        try:
            host = self.agent_host_edit.text().strip() or "127.0.0.1"
            port = int(self.agent_port_edit.text().strip() or "8080")
            options = AgentClientOptions(
                base_url=f"http://{host}:{port}",
                model=self.report_model_edit.text().strip() or None,
                temperature=float(self.ai_temperature.value()),
            )
            summary_payload = {
                "total_scanned": self._last_summary.total_scanned,
                "processed": len(self._last_results),
                "manual_review": sum(1 for r in self._last_results if r.status == ProcessingStatus.MANUAL_REVIEW or r.category == self._last_summary.manual_review_category),
                "failed": sum(1 for r in self._last_results if r.status == ProcessingStatus.FAILED),
                "unsupported": len(self._last_summary.unsupported_files),
                "categories": {r.category: sum(1 for x in self._last_results if x.category == r.category) for r in self._last_results},
            }
            # create a modal dialog to display streaming chunks
            dialog = QDialog(self)
            dialog.setWindowTitle("Executive Report")
            layout = QVBoxLayout(dialog)
            exec_text = QTextEdit(dialog)
            exec_text.setReadOnly(True)
            layout.addWidget(exec_text)
            dialog.setLayout(layout)
            dialog.show()

            worker = ExecReportWorker(summary_payload, options=options)
            self._exec_worker = worker
            worker.chunk_received.connect(lambda s: exec_text.insertPlainText(s))

            def _on_exec_done() -> None:
                saved = ""
                if self._last_output:
                    try:
                        out_path = Path(self._last_output) / "executive_report.md"
                        out_path.write_text(exec_text.toPlainText(), encoding="utf-8")
                        saved = str(out_path)
                    except Exception:
                        saved = ""
                msg = f"Report complete.\nSaved to: {saved}" if saved else "Report complete."
                QMessageBox.information(self, "Exec Report", msg)

            worker.finished.connect(_on_exec_done)

            def _on_error(err: str) -> None:
                dialog.close()
                QMessageBox.critical(self, "Exec Report Error", err)

            worker.error.connect(_on_error)
            worker.start()
        except Exception as exc:
            QMessageBox.critical(self, "Agent request failed", str(exc))

    def _export_table_csv(self) -> None:
        # Prompt for save location and write current table contents as CSV.
        default_path = (
            str(self._last_output / "invoice_table.csv") if self._last_output else ""
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export table to CSV", default_path, "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                # header
                writer.writerow(_COLUMNS)
                for row in range(self.table.rowCount()):
                    row_values = []
                    for col in range(self.table.columnCount()):
                        item = self.table.item(row, col)
                        row_values.append(item.text() if item is not None else "")
                    writer.writerow(row_values)
            QMessageBox.information(self, "Export complete", f"Wrote CSV to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))


def render_markdown_to_pdf(markdown_text: str, path: str, landscape: bool = True) -> None:
    """Render Markdown to a formatted PDF (headings, tables, bold).

    Uses ``QTextDocument.setMarkdown`` so the PDF contains rendered content, not
    the raw Markdown source. Renders landscape with a small font so wide tables
    fit instead of wrapping into vertical character-soup. Module-level so it is
    unit-testable.
    """
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    if landscape:
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Helvetica", 8))
    doc.setMarkdown(markdown_text)
    # Lay the document out to the printable page width so tables size correctly.
    doc.setPageSize(printer.pageRect(QPrinter.Unit.Point).size())
    doc.print_(printer)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
