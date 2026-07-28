from __future__ import annotations

import inspect
import zoneinfo
from datetime import datetime

import pytest

import batikcraft_studio.auction_time as auction_time
from batikcraft_studio.ui import marketplace_mint_dialog


@pytest.fixture
def missing_timezone_database(monkeypatch, tmp_path):
    """Simulasikan Windows/venv lama tanpa zoneinfo sistem maupun tzdata."""

    original_tzpath = zoneinfo.TZPATH
    zoneinfo.reset_tzpath([str(tmp_path)])
    zoneinfo.ZoneInfo.clear_cache()

    def missing_zone(key: str):
        raise zoneinfo.ZoneInfoNotFoundError(f"No time zone found with key {key}")

    monkeypatch.setattr(auction_time, "available_timezones", lambda: set())
    monkeypatch.setattr(auction_time, "ZoneInfo", missing_zone)
    monkeypatch.setattr(marketplace_mint_dialog, "ZoneInfo", missing_zone)
    try:
        yield
    finally:
        zoneinfo.reset_tzpath(original_tzpath)
        zoneinfo.ZoneInfo.clear_cache()


def test_default_deadline_uses_system_clock_without_tzdata(
    missing_timezone_database,
) -> None:
    value = marketplace_mint_dialog._default_deadline("Asia/Jakarta")

    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
    delta = parsed - datetime.now()
    assert 6 <= delta.days <= 7


def test_naive_deadline_gets_local_offset_without_tzdata(
    missing_timezone_database,
) -> None:
    result = auction_time.local_input_to_iso(
        "2026-08-01 17:00",
        "Asia/Jakarta",
    )

    parsed = datetime.fromisoformat(result)
    assert parsed.replace(tzinfo=None) == datetime(2026, 8, 1, 17, 0)
    assert parsed.utcoffset() is not None


def test_offset_deadline_does_not_need_timezone_database(
    missing_timezone_database,
) -> None:
    value = "2026-08-01T17:00:00+07:00"
    assert auction_time.local_input_to_iso(value, "Asia/Jakarta") == value


def test_missing_database_exposes_system_local_mode(
    missing_timezone_database,
) -> None:
    assert auction_time.timezone_database_missing() is True
    assert auction_time.system_timezone_name() == auction_time.SYSTEM_LOCAL_TIMEZONE

    source = inspect.getsource(marketplace_mint_dialog.MintCurrentProjectDialog._timezone_row)
    assert "timezone_database_missing()" in source
    assert "SYSTEM_LOCAL_TIMEZONE" in source
