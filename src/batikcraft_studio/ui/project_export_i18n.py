"""Translations for recent projects and marketplace export workflows."""

from __future__ import annotations

from batikcraft_studio import i18n as _i18n

_TRANSLATIONS = {
    "id": {
        "file.recent_projects": "Proyek Terbaru",
        "file.recent_empty": "(Belum ada proyek terbaru)",
        "file.recent_clear": "Bersihkan Daftar",
        "file.export_as": "Ekspor Sebagai",
        "file.export_jpg": "Gambar JPG…",
        "file.export_jpeg": "Gambar JPEG…",
        "file.export_nft": "Paket BatikCraft NFT…",
        "dialog.export_image.title": "Ekspor Gambar Proyek",
        "dialog.export_nft.title": "Ekspor Paket BatikCraft NFT",
        "dialog.export_nft.creator_name": "Nama kreator dari proyek",
        "dialog.export_nft.creator_id": "ID/username kreator di web",
        "dialog.export_nft.philosophy": "Filosofi karya batik",
        "dialog.export_nft.motifs": "Motif yang digunakan",
        "dialog.export_nft.colors": "Warna HEX yang digunakan",
        "dialog.export_nft.license": "Lisensi",
        "dialog.export_nft.hint_list": "Pisahkan beberapa nilai dengan koma.",
        "dialog.export_nft.integrity_note": (
            "Identitas proyek, metadata, preview, dan seluruh asset akan diberi "
            "checksum SHA-256. Perubahan apa pun membuat validasi paket gagal. "
            "Checksum bukan tanda tangan digital berbasis kunci publik."
        ),
        "dialog.export_nft.error": "Metadata NFT tidak valid",
        "status.image_exported": "Gambar proyek diekspor: {name}",
        "status.nft_exported": "Paket NFT terverifikasi diekspor: {name}",
        "status.export_failed": "Ekspor gagal",
        "recent.missing.title": "Proyek terbaru tidak ditemukan",
        "recent.missing.message": "File proyek sudah dipindah atau dihapus:\n{path}",
        "recent.open_error": "Proyek terbaru tidak dapat dibuka",
    },
    "en": {
        "file.recent_projects": "Recent Projects",
        "file.recent_empty": "(No recent projects)",
        "file.recent_clear": "Clear List",
        "file.export_as": "Export As",
        "file.export_jpg": "JPG Image…",
        "file.export_jpeg": "JPEG Image…",
        "file.export_nft": "BatikCraft NFT Package…",
        "dialog.export_image.title": "Export Project Image",
        "dialog.export_nft.title": "Export BatikCraft NFT Package",
        "dialog.export_nft.creator_name": "Creator name from project",
        "dialog.export_nft.creator_id": "Creator web ID/username",
        "dialog.export_nft.philosophy": "Batik artwork philosophy",
        "dialog.export_nft.motifs": "Motifs used",
        "dialog.export_nft.colors": "HEX colors used",
        "dialog.export_nft.license": "License",
        "dialog.export_nft.hint_list": "Separate multiple values with commas.",
        "dialog.export_nft.integrity_note": (
            "The project identity, metadata, preview, and every asset will be sealed "
            "with SHA-256 checksums. Any change invalidates the package. A checksum "
            "is not a public-key digital signature."
        ),
        "dialog.export_nft.error": "Invalid NFT metadata",
        "status.image_exported": "Project image exported: {name}",
        "status.nft_exported": "Verified NFT package exported: {name}",
        "status.export_failed": "Export failed",
        "recent.missing.title": "Recent project not found",
        "recent.missing.message": "The project file was moved or deleted:\n{path}",
        "recent.open_error": "Recent project could not be opened",
    },
}


def install_project_export_translations() -> None:
    """Install menu and dialog labels into the application catalog."""

    for language, catalog in _TRANSLATIONS.items():
        _i18n._TRANSLATIONS[language].update(catalog)  # type: ignore[attr-defined]


__all__ = ["install_project_export_translations"]
