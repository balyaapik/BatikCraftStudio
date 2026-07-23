"""Logika dialog pustaka & NFT raster (bagian tanpa Tk)."""

from __future__ import annotations

from datetime import datetime

import pytest

from batikcraft_studio.ui.raster_publish_dialogs import (
    auto_asset_name,
    normalize_price,
)


def test_auto_asset_name_berbasis_waktu():
    name = auto_asset_name("Motif", datetime(2026, 7, 23, 14, 5, 9))
    assert name == "Motif 20260723-140509"


def test_auto_asset_name_prefix_kustom():
    name = auto_asset_name("Kain", datetime(2026, 1, 2, 3, 4, 5))
    assert name.startswith("Kain ")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0.5", "0.5"), ("1,25", "1.25"), ("", "0"), ("10.50", "10.5"), ("3", "3")],
)
def test_normalize_price_valid(raw, expected):
    assert normalize_price(raw) == expected


@pytest.mark.parametrize("bad", ["abc", "-1", "-0.5", "1.2.3"])
def test_normalize_price_menolak(bad):
    with pytest.raises(ValueError):
        normalize_price(bad)
