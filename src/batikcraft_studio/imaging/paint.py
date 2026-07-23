"""Deterministic raster brush and eraser operations for paint layers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from io import BytesIO

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageOps, UnidentifiedImageError

MAX_BRUSH_SIZE = 2048.0
MAX_STROKE_STAMPS = 250_000


class PaintStrokeError(ValueError):
    """Raised when paint-layer input cannot produce a safe raster stroke."""


def create_transparent_canvas_png(width: int, height: int) -> bytes:
    """Return a transparent RGBA PNG with validated positive dimensions."""

    _validate_canvas_size(width, height)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    return _encode_png(image)


def smooth_stroke_points(
    points: Sequence[tuple[float, float]],
    smoothing: float,
) -> tuple[tuple[float, float], ...]:
    """Return endpoint-preserving moving-average smoothing for pointer samples."""

    normalized = _validate_points(points)
    strength = _validate_unit_interval(smoothing, "Smoothing")
    if strength == 0 or len(normalized) < 3:
        return normalized

    radius = max(1, min(8, round(1 + strength * 5)))
    passes = 1 if strength < 0.65 else 2
    result = normalized
    for _ in range(passes):
        refined: list[tuple[float, float]] = [result[0]]
        for index in range(1, len(result) - 1):
            start = max(0, index - radius)
            stop = min(len(result), index + radius + 1)
            neighborhood = result[start:stop]
            average_x = sum(point[0] for point in neighborhood) / len(neighborhood)
            average_y = sum(point[1] for point in neighborhood) / len(neighborhood)
            source_x, source_y = result[index]
            refined.append(
                (
                    source_x + (average_x - source_x) * strength,
                    source_y + (average_y - source_y) * strength,
                )
            )
        refined.append(result[-1])
        result = tuple(refined)
    return result


def apply_paint_stroke(
    content: bytes | bytearray | memoryview,
    *,
    width: int,
    height: int,
    points: Sequence[tuple[float, float]],
    brush_size: float,
    color: str,
    erase: bool = False,
    opacity: float = 1.0,
    hardness: float = 1.0,
    smoothing: float = 0.0,
) -> bytes:
    """Apply one refined brush or eraser stroke and return normalized PNG bytes."""

    _validate_canvas_size(width, height)
    diameter = _validate_brush_size(brush_size)
    rgba = _validate_color(color)
    opacity_value = _validate_unit_interval(opacity, "Opacity", minimum_exclusive=True)
    hardness_value = _validate_unit_interval(hardness, "Hardness")
    smoothing_value = _validate_unit_interval(smoothing, "Smoothing")
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

    image = apply_stroke_to_image(
        image,
        points=points,
        brush_size=diameter,
        color=color,
        erase=erase,
        opacity=opacity_value,
        hardness=hardness_value,
        smoothing=smoothing_value,
    )
    return _encode_png(image)


def apply_stroke_to_image(
    image: Image.Image,
    *,
    points: Sequence[tuple[float, float]],
    brush_size: float,
    color: str,
    erase: bool = False,
    opacity: float = 1.0,
    hardness: float = 1.0,
    smoothing: float = 0.0,
) -> Image.Image:
    """Terapkan satu goresan LANGSUNG ke gambar PIL (tanpa decode/encode PNG).

    Inti bersama: apply_paint_stroke (jalur bytes) memakainya, dan jalur canting
    RASTER memakainya untuk menggambar ke bitmap hidup tanpa alokasi/kliping/
    encode kanvas penuh yang mahal. Hasil visualnya identik dengan sebelumnya.
    """

    rgba = _validate_color(color)
    diameter = _validate_brush_size(brush_size)
    opacity_value = _validate_unit_interval(opacity, "Opacity", minimum_exclusive=True)
    hardness_value = _validate_unit_interval(hardness, "Hardness")
    smoothing_value = _validate_unit_interval(smoothing, "Smoothing")
    working = image if image.mode == "RGBA" else image.convert("RGBA")
    smoothed = smooth_stroke_points(points, smoothing_value)
    stamp_points = _resample_stroke(smoothed, max(0.75, diameter * 0.10))
    color_alpha = rgba[3] / 255
    stroke_opacity = opacity_value if erase else opacity_value * color_alpha

    # Batasi kerja ke KOTAK goresan, bukan kanvas penuh. Mask seukuran kanvas
    # 2048 memakan ~28 ms walau goresannya kecil; dengan kotak terbatas biaya
    # mengikuti besar goresan. Margin >= diameter menjamin cap tidak terpotong,
    # sehingga hasilnya identik piksel dengan mask kanvas penuh.
    margin = diameter + 2
    xs = [p[0] for p in stamp_points] or [0.0]
    ys = [p[1] for p in stamp_points] or [0.0]
    left = max(0, int(min(xs) - margin))
    top = max(0, int(min(ys) - margin))
    right = min(working.width, int(max(xs) + margin) + 1)
    bottom = min(working.height, int(max(ys) + margin) + 1)
    if right <= left or bottom <= top:
        return working
    region_size = (right - left, bottom - top)
    shifted = [(px - left, py - top) for px, py in stamp_points]
    stroke_mask = _build_stroke_mask(
        region_size,
        shifted,
        diameter=diameter,
        opacity=stroke_opacity,
        hardness=hardness_value,
    )
    box = (left, top, right, bottom)
    region = working.crop(box)
    if erase:
        remaining = ImageOps.invert(stroke_mask)
        region.putalpha(ImageChops.multiply(region.getchannel("A"), remaining))
        working.paste(region, (left, top))
        return working
    overlay = Image.new("RGBA", region_size, (*rgba[:3], 0))
    overlay.putalpha(stroke_mask)
    working.paste(Image.alpha_composite(region, overlay), (left, top))
    return working


def _resample_stroke(
    points: Sequence[tuple[float, float]],
    spacing: float,
) -> tuple[tuple[float, float], ...]:
    samples: list[tuple[float, float]] = [points[0]]
    for start, end in zip(points, points[1:], strict=False):
        delta_x = end[0] - start[0]
        delta_y = end[1] - start[1]
        distance = math.hypot(delta_x, delta_y)
        if distance == 0:
            continue
        steps = max(1, math.ceil(distance / spacing))
        if len(samples) + steps > MAX_STROKE_STAMPS:
            raise PaintStrokeError("Stroke contains too many samples.")
        samples.extend(
            (
                start[0] + delta_x * step / steps,
                start[1] + delta_y * step / steps,
            )
            for step in range(1, steps + 1)
        )
    return tuple(samples)


def _build_stroke_mask(
    image_size: tuple[int, int],
    points: Sequence[tuple[float, float]],
    *,
    diameter: int,
    opacity: float,
    hardness: float,
) -> Image.Image:
    mask = Image.new("L", image_size, 0)
    stamp = _create_round_stamp(diameter, opacity=opacity, hardness=hardness)
    stamp_width, stamp_height = stamp.size
    half_width = stamp_width // 2
    half_height = stamp_height // 2

    for x, y in points:
        left = round(x) - half_width
        top = round(y) - half_height
        right = left + stamp_width
        bottom = top + stamp_height
        clipped_left = max(0, left)
        clipped_top = max(0, top)
        clipped_right = min(image_size[0], right)
        clipped_bottom = min(image_size[1], bottom)
        if clipped_left >= clipped_right or clipped_top >= clipped_bottom:
            continue

        source_box = (
            clipped_left - left,
            clipped_top - top,
            clipped_right - left,
            clipped_bottom - top,
        )
        destination_box = (clipped_left, clipped_top, clipped_right, clipped_bottom)
        existing = mask.crop(destination_box)
        incoming = stamp.crop(source_box)
        mask.paste(ImageChops.lighter(existing, incoming), destination_box)
    return mask


def _create_round_stamp(diameter: int, *, opacity: float, hardness: float) -> Image.Image:
    scale = 4 if diameter <= 512 else 2 if diameter <= 1024 else 1
    high_diameter = diameter * scale
    padding = scale * 2
    size = high_diameter + padding * 2
    center = size / 2
    outer_radius = high_diameter / 2
    max_alpha = max(1, min(255, round(opacity * 255)))
    stamp = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(stamp)

    if hardness >= 1:
        draw.ellipse(
            (
                center - outer_radius,
                center - outer_radius,
                center + outer_radius,
                center + outer_radius,
            ),
            fill=max_alpha,
        )
    else:
        inner_radius = outer_radius * hardness
        transition = max(outer_radius - inner_radius, 1.0)
        steps = max(12, min(64, round(transition / scale)))
        for step in range(steps):
            progress = step / max(steps - 1, 1)
            radius = outer_radius - transition * progress
            alpha = round(max_alpha * progress**1.35)
            draw.ellipse(
                (
                    center - radius,
                    center - radius,
                    center + radius,
                    center + radius,
                ),
                fill=alpha,
            )
        if inner_radius > 0:
            draw.ellipse(
                (
                    center - inner_radius,
                    center - inner_radius,
                    center + inner_radius,
                    center + inner_radius,
                ),
                fill=max_alpha,
            )

    final_size = diameter + 4
    return stamp.resize((final_size, final_size), Image.Resampling.LANCZOS)


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


def _validate_unit_interval(
    value: float,
    label: str,
    *,
    minimum_exclusive: bool = False,
) -> float:
    if isinstance(value, bool):
        raise PaintStrokeError(f"{label} must be a finite number.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise PaintStrokeError(f"{label} must be a finite number.") from exc
    minimum_valid = numeric > 0 if minimum_exclusive else numeric >= 0
    if not math.isfinite(numeric) or not minimum_valid or numeric > 1:
        interval = "greater than 0 and at most 1" if minimum_exclusive else "between 0 and 1"
        raise PaintStrokeError(f"{label} must be {interval}.")
    return numeric


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
