"""Zona waktu untuk batas waktu lelang yang dikirim ke BatikCraftWeb.

Creator mengetik batas waktu lelang dalam waktu setempat. Tanpa keterangan zona
waktu, server harus menebak maksudnya — dan tebakan itu bisa meleset berjam-jam
bagi creator di luar zona waktu default marketplace. Modul ini menyimpan zona
waktu pilihan pengguna dan mengubah masukan lokal menjadi ISO-8601 yang sudah
membawa offset eksplisit, sehingga tidak ada lagi yang perlu ditebak.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

__all__ = [
    "AuctionTimeError",
    "TimezonePreference",
    "available_timezones_sorted",
    "is_valid_timezone",
    "local_input_to_iso",
    "system_timezone_name",
]

# Format yang diterima dari kotak isian, dari yang paling longgar ke ISO penuh.
_INPUT_FORMATS = (
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %H:%M",
)

_DEFAULT_TIMEZONE = "Asia/Jakarta"


class AuctionTimeError(ValueError):
    """Masukan batas waktu lelang tidak dapat ditafsirkan."""


def available_timezones_sorted() -> list[str]:
    return sorted(available_timezones())


def is_valid_timezone(name: str) -> bool:
    if not name:
        return False
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return False
    return True


def system_timezone_name() -> str:
    """Zona waktu sistem bila dikenali, jika tidak pakai default marketplace."""
    local = datetime.now().astimezone().tzinfo
    name = getattr(local, "key", "") or str(local or "")
    return name if is_valid_timezone(name) else _DEFAULT_TIMEZONE


def local_input_to_iso(value: str, timezone_name: str) -> str:
    """Ubah waktu lokal yang diketik creator menjadi ISO-8601 beroffset.

    Masukan yang sudah membawa offset dibiarkan apa adanya, karena maksudnya
    sudah tidak ambigu. Masukan kosong menghasilkan string kosong supaya
    pemanggil dapat memperlakukannya sebagai "tanpa batas waktu".
    """
    text = (value or "").strip()
    if not text:
        return ""
    if not is_valid_timezone(timezone_name):
        raise AuctionTimeError(f"Zona waktu tidak dikenal: {timezone_name!r}")

    # Sudah beroffset atau berakhiran Z: tidak perlu ditafsirkan ulang.
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None and parsed.tzinfo is not None:
        return parsed.isoformat()

    for fmt in _INPUT_FORMATS:
        try:
            naive = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=ZoneInfo(timezone_name)).isoformat()

    raise AuctionTimeError(
        "Format waktu tidak dikenali. Contoh yang diterima: "
        "2026-08-01 17:00 atau 2026-08-01T17:00:00+07:00."
    )


class TimezonePreference:
    """Simpan zona waktu pilihan pengguna di berkas konfigurasi Studio."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is not None:
            self.path = Path(path)
        else:
            # Impor ditunda agar kelas ini dapat dipakai dan diuji tanpa
            # menyeret seluruh modul jembatan web.
            from batikcraft_studio.web_bridge import _default_config_path

            self.path = _default_config_path()

    def load(self) -> str:
        payload = self._payload()
        name = str(payload.get("auction_timezone") or "")
        return name if is_valid_timezone(name) else system_timezone_name()

    def save(self, timezone_name: str) -> None:
        if not is_valid_timezone(timezone_name):
            raise AuctionTimeError(f"Zona waktu tidak dikenal: {timezone_name!r}")
        payload = self._payload()
        payload["auction_timezone"] = timezone_name
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _payload(self) -> dict:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}
