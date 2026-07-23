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


def test_bbox_identik_termasuk_titik_luar_kanvas():
    """Mask kotak-terbatas harus identik dengan mask kanvas penuh."""

    import random

    from batikcraft_studio.imaging.paint import (
        _build_stroke_mask,
        _resample_stroke,
        _validate_color,
        smooth_stroke_points,
    )
    from PIL import ImageOps

    random.seed(3)
    for _ in range(8):
        base = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        pts = [
            (random.uniform(-10, 310), random.uniform(-10, 310))
            for _ in range(random.randint(1, 5))
        ]
        size = random.choice([3, 8, 24])
        erase = random.random() < 0.3
        opacity = random.choice([0.5, 1.0])
        hardness = random.choice([0.45, 1.0])

        # jalur mask penuh (referensi)
        rgba = _validate_color("#1A140A")
        stamp = _resample_stroke(smooth_stroke_points(pts, 0.0), max(0.75, size * 0.10))
        so = opacity if erase else opacity * (rgba[3] / 255)
        mask = _build_stroke_mask(base.size, stamp, diameter=size, opacity=so, hardness=hardness)
        working = base.copy()
        if erase:
            working.putalpha(ImageChops.multiply(working.getchannel("A"), ImageOps.invert(mask)))
            reference = working
        else:
            overlay = Image.new("RGBA", base.size, (*rgba[:3], 0))
            overlay.putalpha(mask)
            reference = Image.alpha_composite(base.copy(), overlay)

        via_bbox = apply_stroke_to_image(
            base.copy(), points=pts, brush_size=size, color="#1A140A",
            erase=erase, opacity=opacity, hardness=hardness, smoothing=0.0,
        )
        assert ImageChops.difference(reference, via_bbox).getbbox() is None
