"""Bucket fill raster untuk lapis canting (fill kanvas utama)."""

from __future__ import annotations

from PIL import Image, ImageDraw

from batikcraft_studio.imaging.raster_fill import flood_fill_image


def _boxed() -> Image.Image:
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([20, 20, 80, 80], outline=(0, 0, 0, 255), width=3)
    return img


def test_terisi_sampai_batas():
    result = flood_fill_image(_boxed(), 50, 50, "#FF0000")
    assert result.getpixel((50, 50)) == (255, 0, 0, 255)
    assert result.getpixel((30, 30)) == (255, 0, 0, 255)


def test_tidak_bocor_keluar_batas():
    result = flood_fill_image(_boxed(), 50, 50, "#FF0000")
    assert result.getpixel((5, 5)) == (0, 0, 0, 0)


def test_batas_goresan_tetap():
    result = flood_fill_image(_boxed(), 50, 50, "#FF0000")
    assert result.getpixel((20, 50))[3] == 255


def test_base_tidak_diubah():
    base = _boxed()
    flood_fill_image(base, 50, 50, "#FF0000")
    assert base.getpixel((50, 50)) == (0, 0, 0, 0)


def test_klik_di_luar_kanvas_aman():
    result = flood_fill_image(_boxed(), -5, -5, "#00FF00")
    assert result.size == (100, 100)


def test_warna_tuple():
    result = flood_fill_image(_boxed(), 50, 50, (0, 0, 255, 255))
    assert result.getpixel((50, 50)) == (0, 0, 255, 255)
