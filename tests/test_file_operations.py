"""Tests for safe file placement and collision handling."""

from __future__ import annotations

from invoice_sorter.constants import safe_folder_name
from invoice_sorter.file_operations import (
    category_dir,
    place_file,
    unique_target_path,
)


def test_safe_folder_names():
    assert safe_folder_name("Auto / Mobilität") == "Auto_Mobilitaet"
    assert safe_folder_name("Software / Cloud Services") == "Software_Cloud_Services"
    assert safe_folder_name("Unklar / Manuell prüfen") == "Unklar_Manuell_pruefen"
    assert safe_folder_name("Haushalt") == "Haushalt"


def test_unique_target_path_resolves_collisions(tmp_path):
    target_dir = tmp_path
    (target_dir / "invoice.pdf").touch()
    first = unique_target_path(target_dir, "invoice.pdf")
    assert first.name == "invoice_001.pdf"
    first.touch()
    second = unique_target_path(target_dir, "invoice.pdf")
    assert second.name == "invoice_002.pdf"


def test_place_file_copy(tmp_path):
    src = tmp_path / "in" / "doc.pdf"
    src.parent.mkdir()
    src.write_text("hello")
    out = tmp_path / "out"
    target = place_file(src, out, "Internet", dry_run=False, move=False)
    assert target.exists()
    assert src.exists()  # copy, not move
    assert target.parent == category_dir(out, "Internet")


def test_place_file_dry_run_creates_nothing(tmp_path):
    src = tmp_path / "in" / "doc.pdf"
    src.parent.mkdir()
    src.write_text("hello")
    out = tmp_path / "out"
    target = place_file(src, out, "Internet", dry_run=True, move=False)
    assert not target.exists()
    assert not (out / "Sorted_Invoices").exists()
