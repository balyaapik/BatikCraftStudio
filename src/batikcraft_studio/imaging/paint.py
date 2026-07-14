"""Deterministic raster brush and eraser operations for paint layers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from io import BytesIO

from PIL import Image, ImageColor, ImageDraw, UnidentifiedImageError

MAX_BRUSH_SIZE = 2048.0


class PaintStrokeError(ValueError):
    """Raised when paint-layer input cannot produce a safe raster stroke."""


def create_transparent_canvas_png(width: int, height: int) -> bytes:
    """Return a transparent RGBA PNG with validated positive dimensions."""

    _validate_canvas_size(width, height)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    return _encode_png(image)


def apply_paint_stroke(
    content: bytes | bytearray | memoryview,
    *,
    width: int,
    height: int,
    points: Sequence[tuple[float, float]],
    brush_size: float,
    color: str,
    erase: bool = False,
) -> bytes:
    """Apply one round brush or eraser stroke and return normalized PNG bytes."""

    _validate_canvas_size(width, height)
    normalized_points = _validate_points(points)
    diameter = _validate_brush_size(brush_size)
    rgba = _validate_color(color)
    if not isinstance(erase, bool):
        raise PaintStrokeError("erase must be a boolean.")

    raw = bytes(content)
    if not raw:
        raise PaintStrokeError("Paint-layer content must not be empty.")
    try:
        with Image.open(BytesIO(raw)) as source:
            source.load()
            image = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PaintStrokeError("Paint-layer content is not a readable image.") from exc
    if image.size != (width, height):
        raise PaintStrokeError("Paint-layer dimensions must match the project canvas.")

    pixel_points = [(round(x), round(y)) for x, y in normalized_points]
    if erase:
        _erase_round_stroke(image, pixel_points, diameter)
    else:
        _draw_round_stroke(image, pixel_points, diameter, rgba)
    return _encode_png(image)


def _draw_round_stroke(
    image: Image.Image,
    points: list[tuple[int, int]],
    diameter: int,
    color: tuple[int, int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    if len(points) > 1:
        draw.line(points, fill=color, width=diameter, joint="curve")
    radius = diameter / 2
    for x, y in points:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def _erase_round_stroke(
    image: Image.Image,
    points: list[tuple[int, int]],
    diameter: int,
) -> None:
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    if len(points) > 1:
        draw.line(points, fill=255, width=diameter, joint="curve")
    radius = diameter / 2
    for x, y in points:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    image.paste((0, 0, 0, 0), (0, 0, image.width, image.height), mask)


def _validate_canvas_size(width: int, height: int) -> None:
    for label, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise PaintStrokeError(f"Canvas {label} must be a positive integer.")


def _validate_points(points: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    if isinstance(points, (str, bytes, bytearray)) or not isinstance(points, Sequence):
        raise PaintStrokeError("Stroke points must be a sequence of coordinate pairs.")
    normalized: list[tuple[float, float]] = []
    for index, point in enumerate(points):
        if not isinstance(point, Sequence) or len(point) != 2:
            raise PaintStrokeError(f"Stroke point {index} must contain x and y coordinates.")
        x, y = point
        if isinstance(x, bool) or isinstance(y, bool):
            raise PaintStrokeError(f"Stroke point {index} must contain finite numbers.")
        try:
            normalized_point = (float(x), float(y))
        except (TypeError, ValueError) as exc:
            raise PaintStrokeError(f"Stroke point {index} must contain finite numbers.") from exc
        if not all(math.isfinite(value) for value in normalized_point):
            raise PaintStrokeError(f"Stroke point {index} must contain finite numbers.")
        normalized.append(normalized_point)
    if not normalized:
        raise PaintStrokeError("A stroke must contain at least one point.")
    return tuple(normalized)


def _validate_brush_size(value: float) -> int:
    if isinstance(value, bool):
        raise PaintStrokeError("Brush size must be a finite number.")
    try:
        size = float(value)
    except (TypeError, ValueError) as exc:
        raise PaintStrokeError("Brush size must be a finite number.") from exc
    if not math.isfinite(size) or not 1.0 <= size <= MAX_BRUSH_SIZE:
        raise PaintStrokeError(f"Brush size must be between 1 and {MAX_BRUSH_SIZE:g} pixels.")
    return max(1, round(size))


def _validate_color(value: str) -> tuple[int, int, int, int]:
    if not isinstance(value, str):
        raise PaintStrokeError("Brush color must be a CSS-style color string.")
    try:
        rgb = ImageColor.getrgb(value)
    except (TypeError, ValueError) as exc:
        raise PaintStrokeError("Brush color is invalid.") from exc
    if len(rgb) == 4:
        return rgb
    return (*rgb, 255)


def _encode_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
