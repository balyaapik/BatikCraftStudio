"""Bilingual labels for Structured Batification foundations."""

from __future__ import annotations

from batikcraft_studio import i18n as _i18n

_TRANSLATIONS = {
    "id": {
        "menu.ai": "AI Batik",
        "ai.batify_object": "Batifikasi Objek Terpilih…",
        "ai.batify_group": "Batifikasi Lapis / Folder…",
        "ai.rerender": "Render Ulang Komponen",
        "ai.show_source": "Tampilkan Sumber Editable",
        "ai.show_latest": "Tampilkan Render Terbaru",
        "ai.reset": "Reset Batification…",
        "ai.dialog.object_title": "Batifikasi Objek Terpilih",
        "ai.dialog.group_title": "Batifikasi Lapis / Folder",
        "ai.dialog.provider": "Provider",
        "ai.dialog.provider_local": "Renderer fondasi lokal (belum model AI final)",
        "ai.dialog.style": "Gaya Batik",
        "ai.dialog.strength": "Kekuatan Batifikasi",
        "ai.dialog.density": "Kepadatan Isen",
        "ai.dialog.preserve_palette": "Pertahankan warna sumber",
        "ai.dialog.add_filler": "Buat komponen isen/filler terpisah",
        "ai.dialog.primary": "Warna utama",
        "ai.dialog.secondary": "Warna sekunder",
        "ai.dialog.seed": "Seed",
        "ai.dialog.prompt": "Arahan gaya / prompt",
        "ai.dialog.render": "Render Terstruktur",
        "ai.dialog.foundation_note": (
            "Fondasi ini menjaga source, render, dan filler sebagai objek terpisah. "
            "Provider AI final dapat dipasang kemudian tanpa mengubah struktur proyek."
        ),
        "ai.style.classic": "Klasik",
        "ai.style.pesisir": "Pesisir",
        "ai.style.indigo": "Indigo",
        "ai.style.modern": "Modern",
        "ai.style.geometric": "Geometris",
        "ai.status.rendered": "Batifikasi selesai: {name}, versi {version}.",
        "ai.status.group_rendered": "{count} komponen selesai dibatifikasi.",
        "ai.status.rerendered": "Komponen dirender ulang ke versi {version}.",
        "ai.status.source_shown": "Sumber editable ditampilkan: {name}.",
        "ai.status.latest_shown": "Render terbaru versi {version} ditampilkan.",
        "ai.status.reset": "Batification direset ke sumber editable.",
        "ai.reset.title": "Reset Batification",
        "ai.reset.confirm": (
            "Hapus semua versi render dan komponen AI untuk sumber ini? "
            "Tindakan ini dapat diurungkan dengan Ctrl+Z."
        ),
    },
    "en": {
        "menu.ai": "Batik AI",
        "ai.batify_object": "Batify Selected Object…",
        "ai.batify_group": "Batify Layer / Folder…",
        "ai.rerender": "Re-render Component",
        "ai.show_source": "Show Editable Source",
        "ai.show_latest": "Show Latest Render",
        "ai.reset": "Reset Batification…",
        "ai.dialog.object_title": "Batify Selected Object",
        "ai.dialog.group_title": "Batify Layer / Folder",
        "ai.dialog.provider": "Provider",
        "ai.dialog.provider_local": "Local foundation renderer (not the final AI model)",
        "ai.dialog.style": "Batik Style",
        "ai.dialog.strength": "Batification Strength",
        "ai.dialog.density": "Isen Density",
        "ai.dialog.preserve_palette": "Preserve source colors",
        "ai.dialog.add_filler": "Create a separate isen/filler component",
        "ai.dialog.primary": "Primary color",
        "ai.dialog.secondary": "Secondary color",
        "ai.dialog.seed": "Seed",
        "ai.dialog.prompt": "Style direction / prompt",
        "ai.dialog.render": "Structured Render",
        "ai.dialog.foundation_note": (
            "This foundation keeps source, render, and filler as separate objects. "
            "A final AI provider can be connected later without changing project structure."
        ),
        "ai.style.classic": "Classic",
        "ai.style.pesisir": "Coastal",
        "ai.style.indigo": "Indigo",
        "ai.style.modern": "Modern",
        "ai.style.geometric": "Geometric",
        "ai.status.rendered": "Batification complete: {name}, version {version}.",
        "ai.status.group_rendered": "{count} components were Batik-rendered.",
        "ai.status.rerendered": "Component re-rendered as version {version}.",
        "ai.status.source_shown": "Editable source shown: {name}.",
        "ai.status.latest_shown": "Latest render version {version} shown.",
        "ai.status.reset": "Batification reset to the editable source.",
        "ai.reset.title": "Reset Batification",
        "ai.reset.confirm": (
            "Remove all render versions and AI components for this source? "
            "This action can be undone with Ctrl+Z."
        ),
    },
}


def install_structured_batification_translations() -> None:
    """Install labels into the dependency-free application catalog."""

    for language, catalog in _TRANSLATIONS.items():
        _i18n._TRANSLATIONS[language].update(catalog)  # type: ignore[attr-defined]


__all__ = ["install_structured_batification_translations"]
