"""Pustaka dari dokumen raster PENUH (bukan objek per objek)."""

from __future__ import annotations

import io

from PIL import Image

from batikcraft_studio.assets.raster_document_library import (
    add_document_to_library,
    flatten_to_png_bytes,
)
from batikcraft_studio.imaging.raster_document import RasterDocument


def _doc() -> RasterDocument:
    doc = RasterDocument(width=120, height=90, background_color="#FFFFFF")
    doc.active_layer.composite(Image.new("RGBA", (40, 40), (200, 50, 50, 255)), (10, 10))
    doc.add_layer()
    doc.active_layer.composite(Image.new("RGBA", (30, 30), (50, 50, 200, 255)), (60, 40))
    return doc


def test_flatten_menghasilkan_png_dokumen_penuh():
    data = flatten_to_png_bytes(_doc())
    image = Image.open(io.BytesIO(data))
    image.load()

    assert image.mode == "RGB"
    assert image.size == (120, 90)
    assert image.getpixel((30, 30)) == (200, 50, 50)  # layer bawah
    assert image.getpixel((70, 50)) == (50, 50, 200)  # layer atas menimpa
    assert image.getpixel((110, 80)) == (255, 255, 255)  # latar


def test_add_document_meneruskan_flatten_dan_pack(monkeypatch):
    captured = {}

    class _FakeStore:
        def __init__(self, library):
            self.library = library

        def import_image(self, filename, content, *, category, pack_id):
            captured.update(
                filename=filename, content=content, category=category, pack_id=pack_id
            )
            return "RECORD"

    import batikcraft_studio.assets.raster_document_library as module

    monkeypatch.setattr(module, "PersonalAssetStore", _FakeStore)

    result = add_document_to_library(
        object(), _doc(), pack_id="user-lib-x", name="Kawung", category="motif-pokok"
    )

    assert result == "RECORD"
    assert captured["pack_id"] == "user-lib-x"
    assert captured["category"] == "motif-pokok"
    assert captured["filename"] == "Kawung.png"
    image = Image.open(io.BytesIO(captured["content"]))
    image.load()
    assert image.size == (120, 90)


def test_nama_kosong_dapat_nama_default(monkeypatch):
    captured = {}

    class _FakeStore:
        def __init__(self, library):
            pass

        def import_image(self, filename, content, *, category, pack_id):
            captured["filename"] = filename
            return "R"

    import batikcraft_studio.assets.raster_document_library as module

    monkeypatch.setattr(module, "PersonalAssetStore", _FakeStore)
    add_document_to_library(object(), _doc(), pack_id="p", name="   ")

    assert captured["filename"] == "dokumen.png"
