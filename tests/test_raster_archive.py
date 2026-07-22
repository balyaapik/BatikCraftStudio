"""Simpan/muat dokumen raster (.batikpaint)."""

from __future__ import annotations

import pytest
from PIL import Image, ImageChops

from batikcraft_studio.imaging.raster_document import RasterDocument
from batikcraft_studio.persistence.raster_archive import (
    PAINT_EXTENSION,
    RasterArchiveError,
    load_raster_document,
    save_raster_document,
)


def _doc() -> RasterDocument:
    doc = RasterDocument(width=300, height=200, background_color="#EEDDCC")
    doc.active_layer.composite(Image.new("RGBA", (80, 80), (255, 0, 0, 255)), (20, 20))
    doc.add_layer("Motif 2")
    doc.active_layer.composite(Image.new("RGBA", (60, 60), (0, 0, 255, 200)), (100, 50))
    doc.layers[1] = doc.layers[1].with_meta(opacity=0.5, visible=False)
    doc.set_active(doc.layers[1].layer_id)
    return doc


def test_ekstensi_ditambahkan_otomatis(tmp_path):
    saved = save_raster_document(tmp_path / "karya", RasterDocument(width=64, height=64))
    assert saved.suffix == PAINT_EXTENSION


def test_round_trip_metadata(tmp_path):
    doc = _doc()
    loaded = load_raster_document(save_raster_document(tmp_path / "k", doc))

    assert (loaded.width, loaded.height) == (300, 200)
    assert loaded.background_color == "#EEDDCC"
    assert loaded.active_index == 1
    assert loaded.layers[1].name == "Motif 2"
    assert loaded.layers[1].opacity == pytest.approx(0.5)
    assert loaded.layers[1].visible is False


def test_round_trip_piksel_identik(tmp_path):
    doc = _doc()
    loaded = load_raster_document(save_raster_document(tmp_path / "k", doc))

    for asli, dimuat in zip(doc.layers, loaded.layers):
        assert ImageChops.difference(asli.image, dimuat.image).getbbox() is None


def test_id_layer_dipertahankan(tmp_path):
    doc = _doc()
    loaded = load_raster_document(save_raster_document(tmp_path / "k", doc))

    assert [layer.layer_id for layer in loaded.layers] == [
        layer.layer_id for layer in doc.layers
    ]


def test_berkas_rusak_ditolak(tmp_path):
    bad = tmp_path / "rusak.batikpaint"
    bad.write_bytes(b"bukan zip")

    with pytest.raises(RasterArchiveError):
        load_raster_document(bad)


def test_berkas_hilang_ditolak(tmp_path):
    with pytest.raises(RasterArchiveError):
        load_raster_document(tmp_path / "tidakada.batikpaint")


def test_simpan_atomik_tidak_merusak_berkas_lama(tmp_path):
    target = tmp_path / "k.batikpaint"
    save_raster_document(target, _doc())
    ukuran_awal = target.stat().st_size

    # Simpan lagi berhasil; berkas tetap sah.
    save_raster_document(target, RasterDocument(width=100, height=100))
    assert target.is_file()
    loaded = load_raster_document(target)
    assert (loaded.width, loaded.height) == (100, 100)
    assert ukuran_awal > 0
