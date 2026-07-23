"""apply_stroke_to_image: inti goresan berbasis gambar (jalur canting raster).

Harus identik dengan jalur bytes lama (apply_paint_stroke), tapi tanpa
decode/encode/kliping kanvas penuh yang mahal.
"""

from __future__ import annotations

import io

from PIL import Image, ImageChops

from batikcraft_studio.imaging.paint import apply_paint_stroke, apply_stroke_to_image


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _rgba(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image.convert("RGBA")


def test_kuas_identik_dengan_jalur_bytes():
    base = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    kw = dict(
        points=[(30.0, 30.0), (60.0, 80.0), (120.0, 100.0)],
        brush_size=10,
        color="#FF0000",
        opacity=0.9,
        hardness=0.8,
        smoothing=0.3,
    )

    via_bytes = _rgba(apply_paint_stroke(_png(base), width=200, height=200, **kw))
    via_image = apply_stroke_to_image(base.copy(), **kw).convert("RGBA")

    assert ImageChops.difference(via_bytes, via_image).getbbox() is None


def test_penghapus_identik_dengan_jalur_bytes():
    filled = Image.new("RGBA", (200, 200), (0, 100, 200, 255))
    kw = dict(
        points=[(30.0, 30.0), (60.0, 80.0), (120.0, 100.0)],
        brush_size=20,
        color="#FFFFFF",
        erase=True,
        opacity=1.0,
        hardness=1.0,
        smoothing=0.0,
    )

    via_bytes = _rgba(apply_paint_stroke(_png(filled), width=200, height=200, **kw))
    via_image = apply_stroke_to_image(filled.copy(), **kw).convert("RGBA")

    assert ImageChops.difference(via_bytes, via_image).getbbox() is None


def test_meninggalkan_tanda():
    base = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    result = apply_stroke_to_image(
        base, points=[(50.0, 50.0)], brush_size=20, color="#00FF00", opacity=1.0
    )
    assert result.getpixel((50, 50))[1] > 0
