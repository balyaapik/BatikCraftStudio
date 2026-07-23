"""Bucket fill (isi ember) untuk bitmap layer canting raster.

Fill di kanvas utama dulu mencari OBJEK tertutup untuk diwarnai. Setelah goresan
menjadi raster (satu bitmap, bukan objek per goresan), fill bekerja langsung
pada piksel: klik di dalam area tertutup goresan, area itu terisi sampai batas.

Masalah klasiknya: tepi goresan ber-antialias (semi-transparan), sehingga flood
fill berhenti SEBELUM tepi dan menyisakan cincin tak terisi. Solusinya: mask
hasil flood fill DILEBARKAN beberapa piksel, lalu warna isian diletakkan DI
BAWAH goresan — tepi lembut goresan menimpa isian, jadi tidak ada celah dan
tepi tetap halus.
"""

from __future__ import annotations

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter

DEFAULT_TOLERANCE = 48
DEFAULT_EXPAND = 3


def flood_fill_image(
    image: Image.Image,
    x: int,
    y: int,
    color: str | tuple[int, int, int, int],
    *,
    tolerance: int = DEFAULT_TOLERANCE,
    expand: int = DEFAULT_EXPAND,
) -> Image.Image:
    """Isi area sewarna yang terhubung di titik (x, y). Kembalikan gambar BARU.

    Base tidak diubah. Isian dilebarkan ``expand`` piksel ke dalam tepi goresan
    lalu diletakkan di bawah goresan, sehingga tidak ada cincin tak terisi.
    """

    if isinstance(color, str):
        rgb = ImageColor.getrgb(color)
        fill = (rgb[0], rgb[1], rgb[2], 255) if len(rgb) == 3 else rgb
    else:
        fill = tuple(color)
    base = image.convert("RGBA").copy()
    if not (0 <= x < base.width and 0 <= y < base.height):
        return base

    # 1. Flood fill pada salinan memakai warna penanda untuk mendapatkan MASK
    #    area yang terisi (bukan hasil akhirnya).
    sentinel = (255, 0, 255, 255)
    if base.getpixel((int(x), int(y))) == sentinel:
        sentinel = (0, 255, 255, 255)
    probe = base.copy()
    ImageDraw.floodfill(probe, (int(x), int(y)), sentinel, thresh=float(tolerance))
    difference = ImageChops.difference(probe, base).convert("L")
    mask = difference.point(lambda v: 255 if v > 0 else 0)
    if mask.getbbox() is None:
        return base

    # 2. Lebarkan mask agar menjangkau KE BAWAH tepi goresan yang ber-antialias.
    if expand > 0:
        mask = mask.filter(ImageFilter.MaxFilter(2 * expand + 1))

    # 3. Letakkan warna isian di bawah goresan: isian dulu, base di atasnya.
    #    Tepi lembut goresan menimpa isian -> mulus tanpa celah.
    underlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    solid = Image.new("RGBA", base.size, fill)
    underlay.paste(solid, (0, 0), mask)
    underlay.alpha_composite(base)
    return underlay


__all__ = ["DEFAULT_EXPAND", "DEFAULT_TOLERANCE", "flood_fill_image"]