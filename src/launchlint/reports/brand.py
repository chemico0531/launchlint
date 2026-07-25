"""Brand / white-label configuration for LaunchLint reports."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


@dataclass
class BrandConfig:
    """White-label configuration for PDF/HTML reports.

    Values can be loaded from JSON and then overridden via CLI flags.
    """

    agency_name: str = "LaunchLint"
    agency_contact: str = ""
    logo: str = ""  # path or URL
    accent_color: str = "#2563EB"
    client_name: str = ""
    report_title: str = "Pre-Launch Audit Report"
    page_size: str = "A4"  # "A4" or "Letter"
    hide_branding: bool = False

    # PDF margins in mm
    margin_mm: float = 20.0

    def __post_init__(self) -> None:
        if not _is_valid_hex(self.accent_color):
            raise ValueError(
                f"Invalid accent_color {self.accent_color!r}; expected hex like #2563EB"
            )
        self.page_size = self.page_size.upper()
        if self.page_size not in ("A4", "LETTER"):
            raise ValueError(f"Invalid page_size {self.page_size!r}; expected A4 or Letter")

    def merge_overrides(self, **kwargs: Any) -> "BrandConfig":
        """Return a new BrandConfig with non-empty overrides applied."""
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        for key, value in kwargs.items():
            if key not in data:
                raise ValueError(f"Unknown brand override: {key}")
            if value not in (None, ""):
                data[key] = value
        return BrandConfig(**data)

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def _is_valid_hex(color: str) -> bool:
    return bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", color))


def load_brand_config(path: str | Path | None) -> BrandConfig:
    """Load brand config from JSON, or return defaults if path is None/missing."""
    if not path:
        return BrandConfig()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Brand config not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Brand config JSON must be an object")
    # Only accept known fields
    known = {f.name for f in fields(BrandConfig)}
    cleaned = {k: v for k, v in data.items() if k in known}
    return BrandConfig(**cleaned)
