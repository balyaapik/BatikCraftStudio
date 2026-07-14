"""Translations for direct palette, fill, stroke, and layer drag controls."""

from __future__ import annotations

from batikcraft_studio import i18n as _i18n

_TRANSLATIONS = {
    "id": {
        "toolbox.fill": "Fill",
        "direct.color": "Warna aktif",
        "direct.color_target": "Warna diterapkan ke",
        "direct.target.auto": "Otomatis",
        "direct.target.fill": "Isi",
        "direct.target.stroke": "Garis",
        "direct.brush_size": "Ukuran alat",
        "direct.softness": "Kelembutan kuas",
        "direct.smoothing": "Kehalusan garis",
        "direct.outline": "Tampilkan garis tepi",
        "direct.outline_width": "Lebar garis tepi",
        "direct.fill.active": "Fill tool aktif. Klik bidang tertutup untuk mengisinya.",
        "direct.fill.applied": "Fill diterapkan dengan warna {color}.",
        "direct.color.applied": "Warna {color} diterapkan pada {count} objek.",
        "direct.stroke.updated": "Garis tepi diperbarui pada {count} objek.",
        "direct.layer.moved": "Node layer dipindahkan dengan drag-and-drop.",
        "direct.layer.drag_error": "Pemindahan layer gagal: {message}",
    },
    "en": {
        "toolbox.fill": "Fill",
        "direct.color": "Active color",
        "direct.color_target": "Apply color to",
        "direct.target.auto": "Automatic",
        "direct.target.fill": "Fill",
        "direct.target.stroke": "Stroke",
        "direct.brush_size": "Tool size",
        "direct.softness": "Brush softness",
        "direct.smoothing": "Stroke smoothing",
        "direct.outline": "Show outline",
        "direct.outline_width": "Outline width",
        "direct.fill.active": "Fill tool active. Click a closed area to fill it.",
        "direct.fill.applied": "Fill applied with {color}.",
        "direct.color.applied": "Applied {color} to {count} objects.",
        "direct.stroke.updated": "Updated outlines on {count} objects.",
        "direct.layer.moved": "Moved the layer-tree node with drag and drop.",
        "direct.layer.drag_error": "Could not move the layer node: {message}",
    },
}


def install_direct_style_translations() -> None:
    """Install direct-style labels into the shared translation catalog."""

    for language, catalog in _TRANSLATIONS.items():
        _i18n._TRANSLATIONS[language].update(catalog)  # type: ignore[attr-defined]


__all__ = ["install_direct_style_translations"]
