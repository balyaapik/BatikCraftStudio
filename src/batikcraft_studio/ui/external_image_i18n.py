"""Indonesian and English labels for external image insertion workflows."""

from __future__ import annotations

from batikcraft_studio import i18n as _i18n

_TRANSLATIONS = {
    "id": {
        "menu.insert": "Insert",
        "insert.image_file": "Gambar dari File…",
        "insert.image_clipboard": "Gambar dari Clipboard",
    },
    "en": {
        "menu.insert": "Insert",
        "insert.image_file": "Image from File…",
        "insert.image_clipboard": "Image from Clipboard",
    },
}


def install_external_image_translations() -> None:
    """Install external-image menu labels into the shared catalog."""

    for language, catalog in _TRANSLATIONS.items():
        _i18n._TRANSLATIONS[language].update(catalog)  # type: ignore[attr-defined]


__all__ = ["install_external_image_translations"]
