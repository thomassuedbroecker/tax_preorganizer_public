"""Regression test: the exec PDF renders Markdown, never dumps raw Markdown."""

from __future__ import annotations

import re

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pypdf")

from PySide6.QtWidgets import QApplication  # noqa: E402

from invoice_sorter.gui import render_markdown_to_pdf  # noqa: E402
from invoice_sorter.report import RunSummary, build_report  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_exec_pdf_renders_markdown_not_raw_source(qapp, tmp_path):
    md = build_report(
        [],
        RunSummary(
            ai_review=(
                "```markdown\n# AI Review\n\n"
                "## Overall result\n\n- Looks **consistent**.\n```"
            )
        ),
        compact_table=True,
    )
    out = tmp_path / "exec.pdf"
    render_markdown_to_pdf(md, str(out))
    assert out.exists() and out.stat().st_size > 500

    from pypdf import PdfReader

    text = "\n".join((p.extract_text() or "") for p in PdfReader(str(out)).pages)
    # Rendered content present...
    assert "AI Review" in text
    assert re.search(r"Looks\s+consistent", text)
    # ...and raw Markdown markup is gone (not dumped as plain source).
    assert "##" not in text
    assert "|---" not in text
    assert "| Telekom |" not in text
