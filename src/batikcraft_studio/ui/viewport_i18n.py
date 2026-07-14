"""Indonesian and English labels for zoom, grid, rulers, and batch edit actions."""

from __future__ import annotations

from batikcraft_studio import i18n as _i18n

_TRANSLATIONS = {
    "id": {
        "edit.cut": "Potong",
        "viewport.zoom_in": "Perbesar",
        "viewport.zoom_out": "Perkecil",
        "viewport.zoom_fit": "Pasangkan Canvas",
        "viewport.zoom_actual": "Ukuran Aktual 100%",
        "viewport.grid": "Tampilkan Grid",
        "viewport.ruler": "Tampilkan Ruler",
        "viewport.fit.short": "Fit",
        "viewport.zoom.fit_label": "Fit {percent}%",
        "viewport.grid.on": "Grid canvas ditampilkan.",
        "viewport.grid.off": "Grid canvas disembunyikan.",
        "viewport.ruler.on": "Ruler canvas ditampilkan.",
        "viewport.ruler.off": "Ruler canvas disembunyikan.",
        "viewport.cut": "{count} objek dipotong ke clipboard.",
        "viewport.copied": "{count} objek disalin ke clipboard.",
        "viewport.pasted": "{count} objek ditempel sebagai objek baru.",
        "viewport.deleted": "{count} objek dihapus.",
    },
    "en": {
        "edit.cut": "Cut",
        "viewport.zoom_in": "Zoom In",
        "viewport.zoom_out": "Zoom Out",
        "viewport.zoom_fit": "Fit Canvas",
        "viewport.zoom_actual": "Actual Size 100%",
        "viewport.grid": "Show Grid",
        "viewport.ruler": "Show Rulers",
        "viewport.fit.short": "Fit",
        "viewport.zoom.fit_label": "Fit {percent}%",
        "viewport.grid.on": "Canvas grid shown.",
        "viewport.grid.off": "Canvas grid hidden.",
        "viewport.ruler.on": "Canvas rulers shown.",
        "viewport.ruler.off": "Canvas rulers hidden.",
        "viewport.cut": "Cut {count} objects to the clipboard.",
        "viewport.copied": "Copied {count} objects to the clipboard.",
        "viewport.pasted": "Pasted {count} new objects.",
        "viewport.deleted": "Deleted {count} objects.",
    },
}


def install_viewport_translations() -> None:
    """Install viewport labels into the shared translation catalog."""

    for language, catalog in _TRANSLATIONS.items():
        _i18n._TRANSLATIONS[language].update(catalog)  # type: ignore[attr-defined]


__all__ = ["install_viewport_translations"]
