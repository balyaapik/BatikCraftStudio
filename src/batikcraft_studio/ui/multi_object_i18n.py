"""Indonesian and English labels for multi-object editing."""

from __future__ import annotations

from batikcraft_studio import i18n as _i18n

_TRANSLATIONS = {
    "id": {
        "multi.group": "Kelompokkan Objek",
        "multi.ungroup": "Lepaskan Kelompok Objek",
        "multi.grouped": "{count} objek berhasil dikelompokkan.",
        "multi.ungrouped": "{count} grup berhasil dilepas.",
        "multi.selected": "{count} objek dipilih.",
        "multi.moved": "{count} objek dipindahkan bersama.",
        "multi.badge": "{count} objek",
        "multi.marquee_cancelled": "Seleksi beberapa objek dibatalkan.",
    },
    "en": {
        "multi.group": "Group Objects",
        "multi.ungroup": "Ungroup Objects",
        "multi.grouped": "Grouped {count} objects.",
        "multi.ungrouped": "Ungrouped {count} groups.",
        "multi.selected": "Selected {count} objects.",
        "multi.moved": "Moved {count} objects together.",
        "multi.badge": "{count} objects",
        "multi.marquee_cancelled": "Multi-object selection cancelled.",
    },
}


def install_multi_object_translations() -> None:
    """Install Milestone 4C labels into the shared catalog."""

    for language, catalog in _TRANSLATIONS.items():
        _i18n._TRANSLATIONS[language].update(catalog)  # type: ignore[attr-defined]


__all__ = ["install_multi_object_translations"]
