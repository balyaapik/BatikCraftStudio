"""Bucket fill (isi ember) untuk bitmap layer canting raster.

Fill di kanvas utama dulu mencari OBJEK tertutup untuk diwarnai. Setelah goresan
menjadi raster (satu bitmap, bukan objek per goresan), tidak ada objek untuk
di-fill — jadi fill perlu bekerja langsung pada piksel: klik di dalam area
tertutup goresan, area itu terisi sampai batas goresan.
"""

from __future__ import annotations

from PIL import Image, ImageColor, ImageDraw

DEFAULT_TOLERANCE = 40


def flood_fill_image(
    image: Image.Image,
    x: int,
    y: int,
    color: str | tuple[int, int, int, int],
    *,
    tolerance: int = DEFAULT_TOLERANCE,
) -> Image.Image:
    """Isi area sewarna yang terhubung di titik (x, y). Kembalikan gambar BARU.

    Base tidak diubah (state 'sebelum' untuk undo tetap utuh). Fill berhenti di
    batas goresan karena warnanya berbeda melebihi ``tolerance``.
    """

    if isinstance(color, str):
        rgb = ImageColor.getrgb(color)
        fill = (rgb[0], rgb[1], rgb[2], 255) if len(rgb) == 3 else rgb
    else:
        fill = color
    result = image.convert("RGBA").copy()
    if not (0 <= x < result.width and 0 <= y < result.height):
        return result
    ImageDraw.floodfill(result, (int(x), int(y)), fill, thresh=float(tolerance))
    return result


__all__ = ["DEFAULT_TOLERANCE", "flood_fill_image"]
