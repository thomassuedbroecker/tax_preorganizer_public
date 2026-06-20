"""Load and validate the category configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


class ConfigError(ValueError):
    """Raised when the configuration file is missing or malformed."""


@dataclass(frozen=True)
class Category:
    name: str
    keywords: tuple[str, ...] = ()
    vendors: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    categories: tuple[Category, ...]
    manual_review_category: str
    confidence_threshold: float = 0.5
    default_currency: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def category_names(self) -> list[str]:
        return [c.name for c in self.categories]

    def get(self, name: str) -> Optional[Category]:
        for c in self.categories:
            if c.name == name:
                return c
        return None


def _as_str_tuple(value, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigError(f"{where} must be a list, got {type(value).__name__}")
    return tuple(str(v).strip() for v in value if str(v).strip())


def load_config(path: str | Path) -> Config:
    """Read ``categories.yaml`` (or .json) and return a validated ``Config``."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - exercised via tests
        raise ConfigError(f"Could not parse config {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("Top-level config must be a mapping.")

    raw_categories = data.get("categories")
    if not isinstance(raw_categories, dict) or not raw_categories:
        raise ConfigError("Config must define a non-empty 'categories' mapping.")

    categories: list[Category] = []
    for name, spec in raw_categories.items():
        spec = spec or {}
        if not isinstance(spec, dict):
            raise ConfigError(f"Category '{name}' must be a mapping.")
        categories.append(
            Category(
                name=str(name),
                keywords=_as_str_tuple(spec.get("keywords"), f"categories.{name}.keywords"),
                vendors=_as_str_tuple(spec.get("vendors"), f"categories.{name}.vendors"),
            )
        )

    settings = data.get("settings") or {}
    if not isinstance(settings, dict):
        raise ConfigError("'settings' must be a mapping if present.")

    manual = settings.get("manual_review_category", "Unklar / Manuell prüfen")
    if manual not in {c.name for c in categories}:
        raise ConfigError(
            f"manual_review_category '{manual}' is not defined under categories."
        )

    threshold = settings.get("confidence_threshold", 0.5)
    try:
        threshold = float(threshold)
    except (TypeError, ValueError) as exc:
        raise ConfigError("confidence_threshold must be a number.") from exc
    if not 0.0 <= threshold <= 1.0:
        raise ConfigError("confidence_threshold must be between 0.0 and 1.0.")

    return Config(
        categories=tuple(categories),
        manual_review_category=str(manual),
        confidence_threshold=threshold,
        default_currency=settings.get("default_currency"),
        extra={k: v for k, v in settings.items()
               if k not in {"manual_review_category", "confidence_threshold", "default_currency"}},
    )
