"""Translations for rulers, layer containers, folders, and shape fills."""

from __future__ import annotations

from batikcraft_studio import i18n as _i18n

_TRANSLATIONS = {
    "id": {
        "structure.context.new_layer": "Layer Baru",
        "structure.context.new_folder": "Folder Layer Baru",
        "structure.context.move_to_layer": "Pindahkan ke Layer",
        "structure.context.fill_color": "Fill Color…",
        "structure.context.no_layers": "Belum ada layer tujuan",
        "structure.layer.created": "Layer dibuat: {name}",
        "structure.folder.created": "Folder layer dibuat: {name}",
        "structure.objects.moved": "{count} objek dipindahkan ke layer {layer}.",
        "structure.fill.choose": "Pilih Fill Color",
        "structure.fill.closed_required": (
            "Fill color hanya tersedia untuk rectangle, ellipse, dan polygon tertutup."
        ),
        "structure.fill.applied": "Fill {color} diterapkan ke {count} objek tertutup.",
        "structure.shape.created": "Objek bentuk dibuat: {name}",
        "structure.shape.updated": "Objek bentuk diperbarui: {name}",
        "structure.shape.selected": "Terpilih: {shape}",
    },
    "en": {
        "structure.context.new_layer": "New Layer",
        "structure.context.new_folder": "New Layer Folder",
        "structure.context.move_to_layer": "Move to Layer",
        "structure.context.fill_color": "Fill Color…",
        "structure.context.no_layers": "No destination layers",
        "structure.layer.created": "Layer created: {name}",
        "structure.folder.created": "Layer folder created: {name}",
        "structure.objects.moved": "Moved {count} objects to layer {layer}.",
        "structure.fill.choose": "Choose Fill Color",
        "structure.fill.closed_required": (
            "Fill color is only available for closed rectangles, ellipses, and polygons."
        ),
        "structure.fill.applied": "Applied fill {color} to {count} closed objects.",
        "structure.shape.created": "Shape object created: {name}",
        "structure.shape.updated": "Shape object updated: {name}",
        "structure.shape.selected": "Selected: {shape}",
    },
}


def install_canvas_structure_translations() -> None:
    for language, catalog in _TRANSLATIONS.items():
        _i18n._TRANSLATIONS[language].update(catalog)  # type: ignore[attr-defined]


__all__ = ["install_canvas_structure_translations"]
