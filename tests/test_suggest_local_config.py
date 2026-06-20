"""Tests for the local-config suggestion helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from invoice_sorter.models import ExtractionResult, ExtractionStatus


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "suggest_local_config.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("suggest_local_config", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_analyze_classifies_on_plain_view_when_available(tmp_path, config):
    script = _load_script()
    invoice = tmp_path / "invoice.pdf"
    invoice.write_bytes(b"%PDF-1.4 fake")

    def extract(_path):
        return ExtractionResult(
            text="# Rechnung\n\n| Position | Betrag |\n| --- | --- |\n| misc | 50,00 EUR |",
            classification_text="Rechnung von Telekom fuer DSL Internet Vertrag.",
            status=ExtractionStatus.OK,
            backend="fake",
        )

    manual_files, assigned, unknown = script.analyze(tmp_path, config, extract)

    assert manual_files == []
    assert assigned == {}
    assert unknown == []


def test_reroute_count_classifies_on_plain_view_when_available(tmp_path, config):
    script = _load_script()
    invoice = tmp_path / "invoice.pdf"
    invoice.write_bytes(b"%PDF-1.4 fake")

    def extract(_path):
        return ExtractionResult(
            text="# Rechnung\n\n| Position | Betrag |\n| --- | --- |\n| misc | 50,00 EUR |",
            classification_text="Rechnung von Telekom fuer DSL Internet Vertrag.",
            status=ExtractionStatus.OK,
            backend="fake",
        )

    assert script.reroute_count(tmp_path, config, extract) == 0
