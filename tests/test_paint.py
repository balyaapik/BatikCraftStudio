from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from batikcraft_studio.imaging.paint import (
    PaintStrokeError,
    apply_paint_stroke,
    create_transparent_canvas_png,
    smooth_stroke_points,
)


def _open_rgba(content: bytes) -> Image.Image:
    with Image.open(BytesIO(content)) as source:
        source.load()
        return source.convert("RGBA")


def test_create_transparent_canvas_png_returns_empty_rgba_image() -> None:
    image = _open_rgba(create_transparent_canvas_png(48, 32))

    assert image.size == (48, 32)
    assert image.mode == "RGBA"
    assert image.getchannel("A").getextrema() == (0, 0)


def test_brush_stroke_draws_round_opaque_color() -> None:
    blank = create_transparent_canvas_png(64, 64)

    painted = apply_paint_stroke(
        blank,
        width=64,
        height=64,
        points=((12, 12), (52, 52)),
        brush_size=9,
        color="#A43D2F",
    )
    image = _open_rgba(painted)

    assert image.getpixel((12, 12)) == (164, 61, 47, 255)
    assert image.getpixel((32, 32)) == (164, 61, 47, 255)
    assert image.getpixel((0, 0))[3] == 0


def test_brush_opacity_controls_center_alpha() -> None:
    blank = create_transparent_canvas_png(48, 48)

    painted = apply_paint_stroke(
        blank,
        width=48,
        height=48,
        points=((24, 24),),
        brush_size=14,
        color="#336699",
        opacity=0.4,
    )
    image = _open_rgba(painted)

    red, green, blue, alpha = image.getpixel((24, 24))
    assert (red, green, blue) == (51, 102, 153)
    assert 100 <= alpha <= 104


def test_soft_brush_has_faded_edge_and_solid_center() -> None:
    blank = create_transparent_canvas_png(64, 64)

    painted = apply_paint_stroke(
        blank,
        width=64,
        height=64,
        points=((32, 32),),
        brush_size=20,
        color="#000000",
        hardness=0.0,
    )
    image = _open_rgba(painted)
    center_alpha = image.getpixel((32, 32))[3]
    edge_alpha = image.getpixel((40, 32))[3]

    assert 180 <= center_alpha <= 255
    assert 0 < edge_alpha < center_alpha


def test_smoothing_preserves_endpoints_and_reduces_sharp_corner() -> None:
    points = ((0.0, 0.0), (10.0, 20.0), (20.0, 0.0))

    smoothed = smooth_stroke_points(points, 1.0)

    assert smoothed[0] == points[0]
    assert smoothed[-1] == points[-1]
    assert 0 < smoothed[1][1] < points[1][1]


def test_eraser_stroke_removes_existing_pixels() -> None:
    blank = create_transparent_canvas_png(64, 64)
    painted = apply_paint_stroke(
        blank,
        width=64,
        height=64,
        points=((8, 32), (56, 32)),
        brush_size=15,
        color="#223344",
    )

    erased = apply_paint_stroke(
        painted,
        width=64,
        height=64,
        points=((32, 20), (32, 44)),
        brush_size=11,
        color="#000000",
        erase=True,
    )
    image = _open_rgba(erased)

    assert image.getpixel((32, 32))[3] == 0
    assert image.getpixel((16, 32))[3] == 255


def test_partial_opacity_eraser_reduces_alpha_without_removing_pixel() -> None:
    blank = create_transparent_canvas_png(48, 48)
    painted = apply_paint_stroke(
        blank,
        width=48,
        height=48,
        points=((8, 24), (40, 24)),
        brush_size=15,
        color="#223344",
    )

    erased = apply_paint_stroke(
        painted,
        width=48,
        height=48,
        points=((24, 24),),
        brush_size=11,
        color="#000000",
        erase=True,
        opacity=0.5,
    )
    alpha = _open_rgba(erased).getpixel((24, 24))[3]

    assert 120 <= alpha <= 135


@pytest.mark.parametrize(
    ("points", "brush_size", "color", "message"),
    (
        ((), 10, "#000000", "at least one point"),
        (((1, 2),), 0, "#000000", "between 1"),
        (((1, 2),), 10, "not-a-color", "invalid"),
        (((float("nan"), 2),), 10, "#000000", "finite numbers"),
    ),
)
def test_paint_stroke_rejects_invalid_input(
    points: tuple[tuple[float, float], ...],
    brush_size: float,
    color: str,
    message: str,
) -> None:
    blank = create_transparent_canvas_png(32, 32)

    with pytest.raises(PaintStrokeError, match=message):
        apply_paint_stroke(
            blank,
            width=32,
            height=32,
            points=points,
            brush_size=brush_size,
            color=color,
        )


@pytest.mark.parametrize(
    ("parameter", "value", "message"),
    (
        ("opacity", 0.0, "greater than 0"),
        ("hardness", 1.1, "between 0 and 1"),
        ("smoothing", -0.1, "between 0 and 1"),
    ),
)
def test_paint_stroke_rejects_invalid_refinement_values(
    parameter: str,
    value: float,
    message: str,
) -> None:
    blank = create_transparent_canvas_png(32, 32)
    options = {
        "opacity": 1.0,
        "hardness": 1.0,
        "smoothing": 0.0,
    }
    options[parameter] = value

    with pytest.raises(PaintStrokeError, match=message):
        apply_paint_stroke(
            blank,
            width=32,
            height=32,
            points=((8, 8),),
            brush_size=8,
            color="#000000",
            **options,
        )
