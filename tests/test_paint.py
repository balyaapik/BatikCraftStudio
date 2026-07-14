from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from batikcraft_studio.imaging.paint import (
    PaintStrokeError,
    apply_paint_stroke,
    create_transparent_canvas_png,
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
