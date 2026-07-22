"""Deteksi lokasi ekspor yang rawan (OneDrive/cloud) + reveal di Explorer.

Berkas yang ditulis ke folder tersinkron cloud (OneDrive Files On-Demand) bisa
langsung diubah jadi placeholder online-only setelah aplikasi selesai menulis.
Akibatnya berkas terlihat di Explorer tapi gagal dibuka: 'Windows cannot find
... make sure you typed the name correctly'. Aplikasi menulis dengan benar; yang
mengubahnya adalah klien sinkronisasi.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_CLOUD_MARKERS = ("onedrive", "dropbox", "google drive", "googledrive", "icloud")


def is_cloud_synced_path(path: str | Path) -> bool:
    """Perkiraan apakah *path* berada di folder tersinkron cloud."""

    resolved = str(Path(path).expanduser()).casefold()
    if any(marker in resolved for marker in _CLOUD_MARKERS):
        return True
    # Variabel lingkungan OneDrive menunjuk root sinkronisasi Windows.
    for env in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        root = os.environ.get(env)
        if root:
            try:
                Path(path).expanduser().resolve().relative_to(Path(root).resolve())
                return True
            except (ValueError, OSError):
                continue
    return False


def safe_default_export_dir() -> Path:
    """Folder ekspor bawaan yang kemungkinan besar TIDAK tersinkron cloud."""

    candidates = [Path.home() / "Pictures", Path.home() / "Documents", Path.home()]
    for candidate in candidates:
        try:
            if candidate.is_dir() and not is_cloud_synced_path(candidate):
                return candidate
        except OSError:
            continue
    return Path.home()


def reveal_in_file_manager(path: str | Path) -> bool:
    """Buka folder berisi *path* di file manager. True bila berhasil dijalankan."""

    target = Path(path)
    try:
        if sys.platform.startswith("win"):
            # /select menyoroti berkas; juga memicu hidrasi placeholder OneDrive.
            os.system(f'explorer /select,"{target}"')
            return True
        if sys.platform == "darwin":
            os.system(f'open -R "{target}"')
            return True
        os.system(f'xdg-open "{target.parent}"')
        return True
    except OSError:
        return False


__all__ = [
    "is_cloud_synced_path",
    "reveal_in_file_manager",
    "safe_default_export_dir",
]
