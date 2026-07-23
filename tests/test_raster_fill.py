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


def test_tepi_lembut_tanpa_celah():
    """Regresi: tepi goresan ber-antialias menyisakan cincin tak terisi."""

    import math

    from PIL import ImageFilter

    img = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([20, 20, 100, 100], outline=(0, 0, 0, 255), width=5)
    img = img.filter(ImageFilter.GaussianBlur(1.2))

    result = flood_fill_image(img, 60, 60, "#FF0000")

    celah = 0
    for sudut in range(0, 360, 10):
        for radius in range(0, 55):
            px = int(60 + radius * math.cos(math.radians(sudut)))
            py = int(60 + radius * math.sin(math.radians(sudut)))
            pixel = result.getpixel((px, py))
            if pixel[3] > 200 and pixel[:3] != (255, 0, 0):
                break  # sampai goresan
            if pixel[3] < 200:
                celah += 1
                break
    assert celah == 0
    assert result.getpixel((5, 5))[3] == 0  # tidak bocor keluar


def test_sudut_sempit_ikut_terisi():
    from PIL import ImageFilter

    img = Image.new("RGBA", (150, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(20, 130), (75, 20)], fill=(0, 0, 0, 255), width=6)
    d.line([(130, 130), (75, 20)], fill=(0, 0, 0, 255), width=6)
    d.line([(20, 130), (130, 130)], fill=(0, 0, 0, 255), width=6)
    img = img.filter(ImageFilter.GaussianBlur(1.0))

    result = flood_fill_image(img, 75, 90, "#FF0000")

    assert result.getpixel((75, 90))[:3] == (255, 0, 0)
    tip = result.getpixel((75, 45))
    assert tip[:3] == (255, 0, 0) or tip[3] > 200
    assert result.getpixel((10, 10))[3] == 0
