"""Goresan dirender hanya pada kotak yang disentuhnya, bukan seluruh kanvas.

Test terpenting di sini adalah uji kesetaraan: hasil jalur cepat harus identik
piksel demi piksel dengan jalur kanvas penuh yang lama. Optimisasi render yang
mengubah gambar bukanlah optimisasi, melainkan bug.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from batikcraft_studio.imaging.paint import (
    PaintStrokeError,
    apply_paint_stroke,
    create_transparent_canvas_png,
)
from batikcraft_studio.imaging.stroke_object import (
    _stroke_region,
    render_cropped_stroke,
)

CANVAS = (1200, 900)


def _reference(points, brush_size, color, opacity=1.0, hardness=1.0, smoothing=0.0):
    """Jalur lama: render pada kanvas penuh lalu potong."""
    width, height = CANVAS
    rendered = apply_paint_stroke(
        create_transparent_canvas_png(width, height),
        width=width,
        height=height,
        points=points,
        brush_size=brush_size,
        color=color,
        erase=False,
        opacity=opacity,
        hardness=hardness,
        smoothing=smoothing,
    )
    with Image.open(BytesIO(rendered)) as source:
        source.load()
        image = source.convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    return image.crop(bbox), bbox


def _fast(points, brush_size, color, **kw):
    result = render_cropped_stroke(
        canvas_width=CANVAS[0],
        canvas_height=CANVAS[1],
        points=points,
        brush_size=brush_size,
        color=color,
        opacity=kw.get("opacity", 1.0),
        hardness=kw.get("hardness", 1.0),
        smoothing=kw.get("smoothing", 0.0),
        eraser=kw.get("eraser", False),
    )
    with Image.open(BytesIO(result.content)) as source:
        source.load()
        return source.convert("RGBA"), result


@pytest.mark.parametrize(
    "points,brush,color,extra",
    [
        ([(100.0, 100.0), (300.0, 260.0)], 12.0, "#204060", {}),
        ([(50.0, 50.0), (60.0, 55.0)], 4.0, "#FF0000", {}),
        ([(600.0, 400.0), (620.0, 420.0), (700.0, 500.0)], 30.0, "#00AA55", {}),
        ([(200.0, 200.0), (400.0, 400.0)], 24.0, "#123456", {"hardness": 0.2}),
        ([(200.0, 200.0), (400.0, 400.0)], 18.0, "#123456", {"opacity": 0.45}),
        ([(150.0, 150.0), (250.0, 400.0), (500.0, 200.0)], 16.0, "#654321",
         {"smoothing": 0.8}),
    ],
)
def test_fast_path_matches_full_canvas_render(points, brush, color, extra):
    expected, expected_bbox = _reference(points, brush, color, **extra)
    actual, result = _fast(points, brush, color, **extra)

    assert actual.size == expected.size
    assert actual.tobytes() == expected.tobytes()
    # Posisi di ruang proyek juga harus sama dengan jalur lama.
    assert (result.left, result.top) == (expected_bbox[0], expected_bbox[1])


def test_eraser_stroke_also_matches():
    points = [(300.0, 300.0), (450.0, 380.0)]
    expected, expected_bbox = _reference(points, 20.0, "#FFFFFF")
    actual, result = _fast(points, 20.0, "#000000", eraser=True)

    assert actual.tobytes() == expected.tobytes()
    assert (result.left, result.top) == (expected_bbox[0], expected_bbox[1])


def test_region_is_much_smaller_than_the_canvas():
    left, top, right, bottom = _stroke_region(
        [(100.0, 100.0), (140.0, 130.0)], 10.0, *CANVAS
    )
    region_pixels = (right - left) * (bottom - top)
    canvas_pixels = CANVAS[0] * CANVAS[1]

    # Coretan pendek tidak boleh lagi menyentuh seluruh kanvas.
    assert region_pixels < canvas_pixels / 100


def test_region_is_clipped_to_the_canvas():
    left, top, right, bottom = _stroke_region(
        [(-500.0, -500.0), (50.0, 50.0)], 10.0, *CANVAS
    )

    assert left == 0 and top == 0
    assert right <= CANVAS[0] and bottom <= CANVAS[1]


def test_region_covers_the_brush_radius():
    """Kotak harus melebar sejari-jari kuas, kalau tidak goresan terpotong."""
    left, top, right, bottom = _stroke_region([(500.0, 500.0)], 40.0, *CANVAS)

    assert left <= 500 - 20
    assert right >= 500 + 20


def test_stroke_entirely_outside_the_canvas_is_rejected():
    with pytest.raises(PaintStrokeError):
        render_cropped_stroke(
            canvas_width=CANVAS[0],
            canvas_height=CANVAS[1],
            points=[(-900.0, -900.0), (-800.0, -800.0)],
            brush_size=8.0,
            color="#000000",
            opacity=1.0,
            hardness=1.0,
            smoothing=0.0,
        )


def test_stroke_partially_outside_is_kept_and_clipped():
    _, result = _fast([(-40.0, 60.0), (120.0, 90.0)], 14.0, "#0000FF")

    assert result.left >= 0
    assert result.top >= 0
    assert result.width > 0 and result.height > 0
