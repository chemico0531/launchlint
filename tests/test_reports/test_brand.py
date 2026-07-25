"""Tests for LaunchLint report brand configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from launchlint.reports.brand import BrandConfig, load_brand_config


def test_brand_defaults():
    brand = BrandConfig()
    assert brand.agency_name == "LaunchLint"
    assert brand.accent_color == "#2563EB"
    assert brand.page_size == "A4"


def test_brand_from_dict():
    brand = BrandConfig(
        agency_name="Acme Agency",
        client_name="Client Co",
        accent_color="#FF5733",
        page_size="Letter",
    )
    assert brand.agency_name == "Acme Agency"
    assert brand.client_name == "Client Co"
    assert brand.accent_color == "#FF5733"
    assert brand.page_size == "LETTER"


def test_brand_invalid_color():
    with pytest.raises(ValueError):
        BrandConfig(accent_color="red")
    with pytest.raises(ValueError):
        BrandConfig(accent_color="#GGGGGG")


def test_brand_invalid_page_size():
    with pytest.raises(ValueError):
        BrandConfig(page_size="A3")


def test_merge_overrides(tmp_path: Path):
    brand = BrandConfig(agency_name="Original", accent_color="#000000")
    merged = brand.merge_overrides(agency_name="New", client_name="Client")
    assert merged.agency_name == "New"
    assert merged.client_name == "Client"
    assert merged.accent_color == "#000000"
    # Original unchanged
    assert brand.agency_name == "Original"


def test_load_brand_config(tmp_path: Path):
    config = tmp_path / "brand.json"
    data = {
        "agency_name": "Loaded Agency",
        "accent_color": "#111111",
        "report_title": "Custom Title",
    }
    config.write_text(json.dumps(data), encoding="utf-8")
    brand = load_brand_config(config)
    assert brand.agency_name == "Loaded Agency"
    assert brand.report_title == "Custom Title"
    assert brand.accent_color == "#111111"


def test_load_brand_config_defaults():
    brand = load_brand_config(None)
    assert brand.agency_name == "LaunchLint"


def test_load_brand_config_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_brand_config(tmp_path / "nope.json")
