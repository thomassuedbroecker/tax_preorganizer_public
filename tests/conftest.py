"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from invoice_sorter.config import load_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "categories.yaml"


@pytest.fixture
def config():
    return load_config(CONFIG_PATH)
