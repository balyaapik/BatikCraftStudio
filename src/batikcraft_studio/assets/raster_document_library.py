"""Masukkan dokumen raster PENUH ke pustaka aset.

Sesuai keputusan perombakan: pustaka berasal dari satu dokumen penuh yang sudah
lengkap, bukan dari objek per objek di kanvas. Modul ini meratakan dokumen lalu
menyimpannya sebagai satu aset gambar ke pustaka user yang dipilih.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from batikcraft_studio.assets.library import AssetLibrary
from batikcraft_studio.assets.personal_store import PersonalAssetStore
from batikcraft_studio.imaging.raster_document import RasterDocument


def flatten_to_png_bytes(document: RasterDocument) -> bytes:
    """Ratakan seluruh dokumen menjadi PNG (RGB di atas latar dokumen).

    Hasilnya diverifikasi bisa didekode ulang sebelum dikembalikan, supaya aset
    yang tersimpan di pustaka dijamin PNG yang valid.
    """

    buffer = BytesIO()
    document.flatten().save(buffer, format="PNG")
    data = buffer.getvalue()
    if not data or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Perataan dokumen gagal menghasilkan PNG yang sah.")
    with Image.open(BytesIO(data)) as probe:
        probe.verify()
    return data


def add_document_to_library(
    library: AssetLibrary,
    document: RasterDocument,
    *,
    pack_id: str,
    name: str,
    category: str = "ornamen",
):
    """Ratakan dokumen penuh dan simpan sebagai satu aset ke pustaka *pack_id*.

    Pustaka harus SUDAH dibuat (alur: buat wadah pustaka dulu, baru isi).
    Mengembalikan AssetRecord hasil impor.
    """

    store = PersonalAssetStore(library)
    filename = (name.strip() or "dokumen") + ".png"
    return store.import_image(
        filename,
        flatten_to_png_bytes(document),
        category=category,
        pack_id=pack_id,
    )


__all__ = ["add_document_to_library", "flatten_to_png_bytes"]
