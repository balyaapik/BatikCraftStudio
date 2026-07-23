"""Komposit goresan kuas/penghapus ke SATU bitmap layer canting.

Optimasi untuk aplikasi utama: alih-alih membuat satu objek per goresan (yang
menumpuk jadi ratusan objek dan bikin lag), goresan dileburkan langsung ke satu
bitmap seukuran kanvas milik layer canting. Bitmap itu disimpan sebagai PNG di
dalam arsip .batikcraft (ditunjuk layer.asset_ref) — format tidak berubah.

Logika murni (hanya PIL), jadi bisa diuji tanpa memuat sesi/aplikasi.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageChops


def blank_canvas_png(width: int, height: int) -> bytes:
    """PNG transparan seukuran kanvas — titik awal layer canting raster."""

    buffer = BytesIO()
    Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def _decode(content: bytes) -> Image.Image:
    with Image.open(BytesIO(content)) as image:
        image.load()
        return image.convert("RGBA")


def composite_stroke_onto_canvas(
    base_png: bytes,
    stroke_png: bytes,
    left: int,
    top: int,
    *,
    erase: bool = False,
) -> bytes:
    """Leburkan satu goresan (cropped) ke bitmap kanvas penuh. Kembalikan PNG.

    ``stroke_png`` adalah PNG goresan yang sudah dipotong ke kotak isinya;
    ``left``/``top`` posisinya di kanvas. Untuk penghapus, alfa goresan
    DIKURANGKAN dari kanvas; untuk kuas, di-alpha-composite di atas.
    """

    base = _decode(base_png)
    stroke = _decode(stroke_png)
    if erase:
        # Tempel wilayah, kurangi alfanya dengan alfa goresan, kembalikan.
        region = base.crop((left, top, left + stroke.width, top + stroke.height))
        r, g, b, a = region.split()
        keep = ImageChops.subtract(a, stroke.getchannel("A"))
        region = Image.merge("RGBA", (r, g, b, keep))
        base.paste(region, (left, top))
    else:
        base.alpha_composite(stroke, dest=(left, top))
    buffer = BytesIO()
    base.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


__all__ = ["blank_canvas_png", "composite_stroke_onto_canvas"]
