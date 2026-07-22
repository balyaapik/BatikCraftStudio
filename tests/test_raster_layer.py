"""Model layer raster: menggambar = menulis piksel; resize pertahankan piksel."""

from __future__ import annotations

import pytest
from PIL import Image, ImageChops

from batikcraft_studio.imaging.raster_layer import (
    MAX_RASTER_DIMENSION,
    RasterLayer,
    RasterLayerError,
    flatten_layers,
)


def _solid(size, color):
    return Image.new("RGBA", size, color)


def test_menggambar_menulis_piksel():
    layer = RasterLayer(width=200, height=200)
    layer.composite(_solid((20, 20), (255, 0, 0, 255)), (10, 10))

    assert layer.image.getpixel((15, 15)) == (255, 0, 0, 255)
    assert layer.image.getpixel((0, 0)) == (0, 0, 0, 0)


def test_memperbesar_kanvas_mempertahankan_piksel():
    layer = RasterLayer(width=200, height=200)
    layer.composite(_solid((20, 20), (255, 0, 0, 255)), (10, 10))

    besar = layer.resized_canvas(400, 400, anchor="nw")

    assert besar.image.getpixel((15, 15)) == (255, 0, 0, 255)
    assert besar.image.getpixel((300, 300)) == (0, 0, 0, 0)


def test_piksel_lama_tidak_pernah_buram_saat_resize():
    """Inti aturan 'Resize Canvas': isi lama identik, bukan diregangkan."""

    layer = RasterLayer(width=200, height=200)
    layer.composite(_solid((50, 50), (10, 120, 200, 255)), (30, 30))

    besar = layer.resized_canvas(500, 500, anchor="nw")

    lama = layer.image.crop((0, 0, 200, 200))
    baru = besar.image.crop((0, 0, 200, 200))
    assert ImageChops.difference(lama, baru).getbbox() is None


def test_memperkecil_kanvas_memotong():
    layer = RasterLayer(width=200, height=200)
    layer.composite(_solid((200, 200), (255, 0, 0, 255)), (0, 0))

    kecil = layer.resized_canvas(100, 100, anchor="nw")

    assert kecil.width == 100
    assert kecil.image.getpixel((50, 50)) == (255, 0, 0, 255)


@pytest.mark.parametrize(
    ("anchor", "probe", "warna"),
    [
        ("nw", (10, 10), (0, 255, 0, 255)),
        ("center", (100, 100), (0, 255, 0, 255)),
        ("se", (150, 150), (0, 255, 0, 255)),
    ],
)
def test_anchor_meletakkan_isi_lama(anchor, probe, warna):
    layer = RasterLayer(width=100, height=100)
    layer.composite(_solid((100, 100), (0, 255, 0, 255)), (0, 0))

    besar = layer.resized_canvas(200, 200, anchor=anchor)

    assert besar.image.getpixel(probe) == warna


def test_id_layer_dipertahankan_lintas_resize():
    layer = RasterLayer(width=100, height=100, layer_id="tetap")

    assert layer.resized_canvas(200, 200).layer_id == "tetap"


def test_penghapus_mengurangi_alfa():
    layer = RasterLayer(width=50, height=50)
    layer.composite(_solid((50, 50), (0, 0, 255, 255)), (0, 0))

    layer.erase(Image.new("L", (20, 20), 255), (0, 0))

    assert layer.image.getpixel((5, 5))[3] == 0
    assert layer.image.getpixel((40, 40))[3] == 255


def test_round_trip_png():
    layer = RasterLayer(width=64, height=64, name="Motif")
    layer.composite(_solid((30, 30), (200, 100, 50, 255)), (5, 5))

    restored = RasterLayer.from_png_bytes(
        layer.to_png_bytes(), name="Motif", layer_id="abc"
    )

    assert restored.image.getpixel((10, 10)) == (200, 100, 50, 255)
    assert restored.name == "Motif"
    assert restored.layer_id == "abc"


def test_flatten_dokumen_penuh():
    a = RasterLayer(width=100, height=100)
    a.composite(_solid((100, 100), (255, 0, 0, 255)), (0, 0))
    b = RasterLayer(width=100, height=100)
    b.composite(_solid((50, 50), (0, 0, 255, 255)), (0, 0))

    flat = flatten_layers([a, b], 100, 100, "#FFFFFF")

    assert flat.mode == "RGB"
    assert flat.getpixel((25, 25)) == (0, 0, 255)  # b menimpa a
    assert flat.getpixel((75, 75)) == (255, 0, 0)  # hanya a


def test_flatten_melewati_layer_tak_terlihat():
    a = RasterLayer(width=50, height=50)
    a.composite(_solid((50, 50), (255, 0, 0, 255)), (0, 0))
    b = RasterLayer(width=50, height=50, visible=False)
    b.composite(_solid((50, 50), (0, 0, 255, 255)), (0, 0))

    flat = flatten_layers([a, b], 50, 50, "#FFFFFF")

    assert flat.getpixel((25, 25)) == (255, 0, 0)


@pytest.mark.parametrize("bad", [0, -5, MAX_RASTER_DIMENSION + 1])
def test_dimensi_tak_sah_ditolak(bad):
    with pytest.raises(RasterLayerError):
        RasterLayer(width=bad, height=100)


def test_opasitas_di_luar_rentang_ditolak():
    with pytest.raises(RasterLayerError):
        RasterLayer(width=10, height=10, opacity=1.5)


def test_preset_kanvas_dalam_batas():
    from batikcraft_studio.imaging.canvas_presets import CANVAS_PRESETS

    for preset in CANVAS_PRESETS:
        assert 1 <= preset.width <= MAX_RASTER_DIMENSION
        assert 1 <= preset.height <= MAX_RASTER_DIMENSION


def test_preset_a4_300dpi():
    from batikcraft_studio.imaging.canvas_presets import preset_by_key

    a4 = preset_by_key("a4")
    assert a4 is not None
    assert (a4.width, a4.height) == (2480, 3508)


def test_ukuran_bebas_dijepit():
    from batikcraft_studio.imaging.canvas_presets import clamp_dimension

    assert clamp_dimension(99999) == MAX_RASTER_DIMENSION
    assert clamp_dimension(0) == 1
    assert clamp_dimension(2048) == 2048
