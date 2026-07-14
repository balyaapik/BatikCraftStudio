"""Translation extension for the dockable professional workspace."""

from __future__ import annotations

from batikcraft_studio import i18n as _i18n

_TRANSLATIONS = {
    "id": {
        "dock.tools": "Peralatan Batik",
        "dock.undock": "Lepaskan panel",
        "dock.dock": "Pasang kembali panel",
        "dock.tools_menu": "Dock/Undock Peralatan Batik",
        "dock.assets_menu": "Dock/Undock Pustaka Asset",
        "dock.layers_menu": "Dock/Undock Susunan Lapis",
        "dock.all": "Pasang Semua Panel",
        "toolbox.select": "Seleksi",
        "toolbox.canting": "Canting Lilin",
        "toolbox.brush": "Kuas",
        "toolbox.pencil": "Pensil",
        "toolbox.eraser": "Penghapus",
        "toolbox.line": "Garis",
        "toolbox.rectangle": "Persegi",
        "toolbox.ellipse": "Elips",
        "toolbox.polygon": "Poligon",
        "toolbox.motif": "Cap Motif",
        "toolbox.isen": "Cap Isen",
        "toolbox.options": "Pengaturan Alat…",
        "toolbox.canting_active": "Canting Lilin aktif — preset garis malam yang rapat dan stabil.",
        "toolbox.brush_active": "Kuas aktif — preset gores lembut untuk pewarnaan dan aksen.",
        "toolbox.pencil_active": "Pensil aktif — preset garis tipis dan keras untuk sketsa.",
        "tree.new_tooltip": "Buat folder atau lapis baru",
        "tree.move_up": "Naikkan urutan pilihan",
        "tree.move_down": "Turunkan urutan pilihan",
        "palette.title": "Warna Utama / Sekunder",
        "palette.custom": "Warna Lain…",
        "palette.choose_primary": "Pilih Warna Utama",
        "palette.choose_secondary": "Pilih Warna Sekunder",
        "palette.primary_set": "Warna utama diubah menjadi {color}.",
        "palette.secondary_set": "Warna sekunder diubah menjadi {color}.",
        "palette.swapped": "Warna utama dan sekunder ditukar.",
        "palette.reset": "Warna utama dan sekunder dikembalikan ke palet batik awal.",
    },
    "en": {
        "dock.tools": "Batik Tools",
        "dock.undock": "Undock panel",
        "dock.dock": "Dock panel",
        "dock.tools_menu": "Dock/Undock Batik Tools",
        "dock.assets_menu": "Dock/Undock Asset Library",
        "dock.layers_menu": "Dock/Undock Layer Structure",
        "dock.all": "Dock All Panels",
        "toolbox.select": "Select",
        "toolbox.canting": "Wax Canting",
        "toolbox.brush": "Brush",
        "toolbox.pencil": "Pencil",
        "toolbox.eraser": "Eraser",
        "toolbox.line": "Line",
        "toolbox.rectangle": "Rectangle",
        "toolbox.ellipse": "Ellipse",
        "toolbox.polygon": "Polygon",
        "toolbox.motif": "Motif Stamp",
        "toolbox.isen": "Isen Stamp",
        "toolbox.options": "Tool Settings…",
        "toolbox.canting_active": "Wax Canting active — a tight, stable wax-line preset.",
        "toolbox.brush_active": "Brush active — a soft stroke preset for coloring and accents.",
        "toolbox.pencil_active": "Pencil active — a thin, hard stroke preset for sketching.",
        "tree.new_tooltip": "Create a new folder or layer",
        "tree.move_up": "Move selected item up",
        "tree.move_down": "Move selected item down",
        "palette.title": "Primary / Secondary Colors",
        "palette.custom": "More Colors…",
        "palette.choose_primary": "Choose Primary Color",
        "palette.choose_secondary": "Choose Secondary Color",
        "palette.primary_set": "Primary color changed to {color}.",
        "palette.secondary_set": "Secondary color changed to {color}.",
        "palette.swapped": "Primary and secondary colors swapped.",
        "palette.reset": "Primary and secondary colors reset to the initial Batik palette.",
    },
}

# The core catalog intentionally remains dependency-free and tiny. This extension is
# imported by the professional workspace before any of these keys are rendered.
for _language, _catalog in _TRANSLATIONS.items():
    _i18n._TRANSLATIONS[_language].update(_catalog)  # type: ignore[attr-defined]

__all__: list[str] = []
