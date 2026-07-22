"""Mesin kuas raster: mengecap goresan ke bitmap layer."""

from __future__ import annotations

from PIL import Image

from batikcraft_studio.imaging.brush_engine import BrushEngine, BrushSettings
from batikcraft_studio.imaging.raster_layer import RasterLayer


def test_satu_titik_meninggalkan_tanda():
    layer = RasterLayer(200, 200)
    BrushEngine(BrushSettings(size=20, color="#FF0000")).stroke(layer, [(100, 100)])

    assert layer.image.getpixel((100, 100))[:3] == (255, 0, 0)
    assert layer.image.getpixel((0, 0))[3] == 0


def test_goresan_garis_tidak_berlubang():
    layer = RasterLayer(200, 200)
    BrushEngine(BrushSettings(size=20, color="#FF0000")).stroke(
        layer, [(20, 100), (180, 100)]
    )

    celah = [x for x in range(20, 181, 2) if layer.image.getpixel((x, 100))[3] == 0]
    assert celah == []


def test_penghapus_mengosongkan():
    layer = RasterLayer(100, 100)
    layer.composite(Image.new("RGBA", (100, 100), (0, 0, 255, 255)), (0, 0))

    BrushEngine(BrushSettings(size=30, erase=True)).stroke(layer, [(50, 50)])

    assert layer.image.getpixel((50, 50))[3] == 0
    assert layer.image.getpixel((5, 5))[3] == 255


def test_goresan_kosong_aman():
    layer = RasterLayer(50, 50)
    BrushEngine(BrushSettings()).stroke(layer, [])
    assert layer.image.getbbox() is None


def test_warna_kuas_dihormati():
    layer = RasterLayer(60, 60)
    BrushEngine(BrushSettings(size=10, color="#00AA33")).stroke(layer, [(30, 30)])

    r, g, b, a = layer.image.getpixel((30, 30))
    assert (r, g, b) == (0, 170, 51)
    assert a > 0


def test_koordinat_kanvas_bolak_balik():
    from batikcraft_studio.ui.raster_canvas_widget import (
        project_to_view,
        view_to_project,
    )

    view = project_to_view(150, 220, 40, 60, 0.75)
    proj = view_to_project(view[0], view[1], 40, 60, 0.75)

    assert proj[0] == __import__("pytest").approx(150)
    assert proj[1] == __import__("pytest").approx(220)


def test_fit_zoom_dalam_batas():
    from batikcraft_studio.ui.raster_canvas_widget import fit_zoom

    assert 0.1 <= fit_zoom(4096, 4096, 1600, 900) <= 1.5
    assert fit_zoom(100, 100, 1600, 900) == 1.0
