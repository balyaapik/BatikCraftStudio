"""Translations for contextual tool controls, destructive erasing, and panel tabs."""

from __future__ import annotations

from batikcraft_studio import i18n as _i18n

_TRANSLATIONS = {
    "id": {
        "context.options": "Opsi {tool}",
        "context.click_again": "Klik ikon alat yang sama untuk menyembunyikan atau menampilkan opsi ini.",
        "context.eraser_destructive": "Penghapus mengurangi piksel objek yang disentuh dan tidak membuat objek penutup baru.",
        "context.eraser_object_required": "Klik dan seret langsung pada objek yang ingin dihapus sebagian.",
        "context.eraser_applied": "Sebagian piksel objek {name} telah dihapus.",
    },
    "en": {
        "context.options": "{tool} options",
        "context.click_again": "Click the same tool icon again to hide or show these options.",
        "context.eraser_destructive": "The eraser removes pixels from the touched object instead of creating an overlay object.",
        "context.eraser_object_required": "Click and drag directly on the object you want to erase.",
        "context.eraser_applied": "Erased pixels from {name}.",
    },
}


def install_context_tool_translations() -> None:
    for language, catalog in _TRANSLATIONS.items():
        _i18n._TRANSLATIONS[language].update(catalog)  # type: ignore[attr-defined]


__all__ = ["install_context_tool_translations"]
