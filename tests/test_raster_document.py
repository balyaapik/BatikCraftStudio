"""Dokumen raster + renderer viewport (kanvas gaya MS Paint)."""

from __future__ import annotations

import pytest
from PIL import Image, ImageChops

from batikcraft_studio.imaging.raster_document import RasterDocument
from batikcraft_studio.imaging.raster_layer import RasterLayerError
from batikcraft_studio.imaging.raster_viewport import (
    RasterViewportRenderer,
    ViewportRequest,
)


def _solid(size, color):
    return Image.new("RGBA", size, color)


def test_dokumen_baru_punya_satu_layer():
    doc = RasterDocument(width=256, height=256)
    assert len(doc.layers) == 1
    assert doc.active_layer.name == "Layer 1"


def test_tambah_dan_pindah_layer():
    doc = RasterDocument(width=64, height=64)
    doc.add_layer("Layer 2")
    assert doc.active_index == 1
    doc.set_active(doc.layers[0].layer_id)
    assert doc.active_index == 0
    doc.move_active(1)
    assert doc.layers[1].name == "Layer 1"


def test_tidak_bisa_menghapus_layer_terakhir():
    doc = RasterDocument(width=64, height=64)
    with pytest.raises(RasterLayerError):
        doc.remove_active()


def test_resize_dokumen_mempertahankan_semua_layer():
    doc = RasterDocument(width=200, height=200)
    doc.active_layer.composite(_solid((50, 50), (255, 0, 0, 255)), (10, 10))
    doc.add_layer()
    doc.active_layer.composite(_solid((30, 30), (0, 0, 255, 255)), (0, 0))

    doc.resize_canvas(400, 400, anchor="nw")

    assert doc.width == 400
    assert all(layer.width == 400 for layer in doc.layers)
    assert doc.layers[0].image.getpixel((15, 15)) == (255, 0, 0, 255)


def test_layer_wajib_seukuran_kanvas():
    from batikcraft_studio.imaging.raster_layer import RasterLayer

    with pytest.raises(RasterLayerError):
        RasterDocument(
            width=100,
            height=100,
            layers=[RasterLayer(50, 50)],
        )


def test_render_keluaran_tepat_seukuran_viewport():
    doc = RasterDocument(width=4096, height=4096)
    renderer = RasterViewportRenderer()

    for zoom in (0.3, 1.0, 1.5):
        out = renderer.render(doc, ViewportRequest(0, 0, 1600, 900, zoom))
        assert out.width <= 1600
        assert out.height <= 900


def test_compose_region_identik_dengan_potongan_penuh():
    doc = RasterDocument(width=512, height=512)
    doc.active_layer.composite(_solid((200, 200), (255, 0, 0, 180)), (50, 50))
    doc.add_layer("atas")
    doc.active_layer.composite(_solid((100, 100), (0, 0, 255, 255)), (0, 0))
    doc.set_active(doc.layers[0].layer_id)

    renderer = RasterViewportRenderer()
    box = (40, 40, 300, 300)
    penuh = renderer.compose_full(doc).crop(box)
    region = renderer.compose_region(doc, box)

    assert ImageChops.difference(penuh, region).getbbox() is None


def test_menggambar_tidak_meratakan_ulang_latar():
    """Cache latar: hanya layer aktif yang berubah saat menggambar."""

    doc = RasterDocument(width=256, height=256)
    doc.add_layer("atas")  # aktif = atas; latar = layer bawah
    renderer = RasterViewportRenderer()

    renderer.compose_full(doc)
    signature_awal = renderer._below_signature
    doc.active_layer.composite(_solid((20, 20), (0, 0, 0, 255)), (10, 10))
    renderer.compose_full(doc)

    assert renderer._below_signature == signature_awal


def test_ganti_layer_aktif_membangun_ulang_latar():
    doc = RasterDocument(width=128, height=128)
    doc.add_layer("atas")
    renderer = RasterViewportRenderer()

    renderer.compose_full(doc)
    signature_atas = renderer._below_signature
    doc.set_active(doc.layers[0].layer_id)
    renderer.compose_full(doc)

    assert renderer._below_signature != signature_atas


def test_latar_tak_valid_ditolak():
    with pytest.raises(RasterLayerError):
        RasterDocument(width=64, height=64, background_color="merah")
