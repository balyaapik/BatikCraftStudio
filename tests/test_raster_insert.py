"""Sisipkan gambar sebagai layer baru di dokumen raster."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from batikcraft_studio.imaging.raster_document import RasterDocument
from batikcraft_studio.imaging.raster_insert import (
    build_layer_from_image,
    fit_within,
    insert_image_as_layer,
)
from batikcraft_studio.imaging.raster_layer import RasterLayerError


def _png(size, color):
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_sisip_sebagai_layer_baru_di_tengah():
    doc = RasterDocument(width=200, height=200)
    n = len(doc.layers)

    layer = insert_image_as_layer(doc, _png((40, 40), (255, 0, 0, 255)), name="Motif")

    assert len(doc.layers) == n + 1
    assert doc.active_layer is layer
    assert layer.name == "Motif"
    assert layer.image.getpixel((100, 100)) == (255, 0, 0, 255)  # tengah
    assert layer.image.getpixel((10, 10)) == (0, 0, 0, 0)


def test_gambar_besar_diperkecil():
    layer = build_layer_from_image(
        _png((800, 400), (0, 0, 255, 255)), 200, 200, name="Besar"
    )

    terisi = [
        (x, y)
        for x in range(200)
        for y in range(200)
        if layer.image.getpixel((x, y))[3] > 0
    ]
    xs = [p[0] for p in terisi]
    ys = [p[1] for p in terisi]
    assert max(xs) - min(xs) <= 200
    assert max(ys) - min(ys) <= 110


def test_posisi_kustom():
    doc = RasterDocument(width=100, height=100)
    layer = insert_image_as_layer(doc, _png((20, 20), (0, 255, 0, 255)), position=(5, 5))

    assert layer.image.getpixel((10, 10)) == (0, 255, 0, 255)
    assert layer.image.getpixel((90, 90)) == (0, 0, 0, 0)


def test_gambar_kecil_tidak_diperbesar():
    small = Image.new("RGBA", (10, 10), (1, 2, 3, 255))
    result = fit_within(small, 500, 500)
    assert result.size == (10, 10)


def test_gambar_rusak_ditolak():
    doc = RasterDocument(width=64, height=64)
    with pytest.raises(RasterLayerError):
        insert_image_as_layer(doc, b"bukan gambar")


def test_sisip_disisipkan_di_atas_layer_aktif():
    doc = RasterDocument(width=50, height=50)
    doc.add_layer("kedua")  # active_index = 1
    insert_image_as_layer(doc, _png((10, 10), (255, 255, 0, 255)))

    assert doc.active_index == 2
    assert len(doc.layers) == 3
