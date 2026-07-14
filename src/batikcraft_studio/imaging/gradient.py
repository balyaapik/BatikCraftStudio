"""Non-destructive gradient compositing for BatikCraft objects.

Gradients are stored inside ``LayerObject.properties`` under the key
``"gradient"`` and never create extra objects or modify the original asset.
The original alpha channel is used as a mask so that paint strokes, motifs,
and isen objects preserve their transparency.

Supported fill_mode values
--------------------------
* ``"solid"``           — plain solid color (default; no gradient applied)
* ``"linear_gradient"`` — linear gradient between two colors at an angle
* ``"radial_gradient"`` — radial gradient from a center to an outer color

Gradient dict schema
---------------------
Linear::

    {
        "type": "linear",
        "angle": 45.0,          # degrees, 0 = top→bottom, 90 = left→right
        "start_color": "#4E2A1E",
        "end_color": "#D9A566",
        "start_opacity": 1.0,
        "end_opacity": 0.75,
        "offset_x": 0.0,        # –1.0 … +1.0, relative to object width
        "offset_y": 0.0,
    }

Radial::

    {
        "type": "radial",
        "center_color": "#4E2A1E",
        "outer_color": "#D9A566",
        "center_opacity": 1.0,
        "outer_opacity": 0.75,
        "center_x": 0.5,        # 0.0 … 1.0, relative to object width
        "center_y": 0.5,
        "radius": 0.5,          # relative to max(width, height)
    }
"""

from __future__ import annotations

import math
from io import BytesIO
from typing import Any

from PIL import Image, ImageColor


class GradientError(ValueError):
    """Raised when gradient properties contain invalid values."""


def apply_gradient_to_image(
    image: Image.Image,
    gradient: dict[str, Any],
    fill_mode: str,
) -> Image.Image:
    """Apply a non-destructive gradient overlay using the image's alpha as mask.

    Parameters
    ----------
    image
        Source RGBA image.  Its alpha channel is used as the gradient mask.
    gradient
        Gradient property dict from ``LayerObject.properties["gradient"]``.
    fill_mode
        ``"linear_gradient"`` or ``"radial_gradient"``.

    Returns
    -------
    Image.Image
        A new RGBA image with the gradient composited against the original
        transparency.  The object count and asset bytes are unchanged.
    """
    image = image.convert("RGBA")
    alpha = image.getchannel("A")
    width, height = image.size

    if fill_mode == "linear_gradient":
        gradient_image = _build_linear_gradient(width, height, gradient)
    elif fill_mode == "radial_gradient":
        gradient_image = _build_radial_gradient(width, height, gradient)
    else:
        return image

    # Use the original alpha as the mask — preserve strokes/motif shapes.
    gradient_image.putalpha(alpha)
    return gradient_image


def _build_linear_gradient(
    width: int,
    height: int,
    props: dict[str, Any],
) -> Image.Image:
    angle_deg = float(props.get("angle", 0.0))
    start_color = _parse_color(props.get("start_color", "#000000"), "start_color")
    end_color = _parse_color(props.get("end_color", "#FFFFFF"), "end_color")
    start_opacity = float(props.get("start_opacity", 1.0))
    end_opacity = float(props.get("end_opacity", 1.0))
    offset_x = float(props.get("offset_x", 0.0))
    offset_y = float(props.get("offset_y", 0.0))

    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    result = Image.new("RGBA", (width, height))
    pixels = result.load()
    if pixels is None:
        return result

    # Centre of the object plus the user offset (in image pixels).
    cx = (width / 2) + offset_x * width
    cy = (height / 2) + offset_y * height
    # Half-diagonal — defines the 0→1 projection range.
    half_diag = math.hypot(width, height) / 2

    for y in range(height):
        for x in range(width):
            # Project the vector from center onto the gradient axis.
            dx = x - cx
            dy = y - cy
            t = (dx * sin_a + dy * cos_a) / (2 * half_diag) + 0.5
            t = max(0.0, min(1.0, t))
            r = round(start_color[0] + (end_color[0] - start_color[0]) * t)
            g = round(start_color[1] + (end_color[1] - start_color[1]) * t)
            b = round(start_color[2] + (end_color[2] - start_color[2]) * t)
            a = round((start_opacity + (end_opacity - start_opacity) * t) * 255)
            pixels[x, y] = (r, g, b, a)

    return result


def _build_radial_gradient(
    width: int,
    height: int,
    props: dict[str, Any],
) -> Image.Image:
    center_color = _parse_color(props.get("center_color", "#000000"), "center_color")
    outer_color = _parse_color(props.get("outer_color", "#FFFFFF"), "outer_color")
    center_opacity = float(props.get("center_opacity", 1.0))
    outer_opacity = float(props.get("outer_opacity", 1.0))
    cx = float(props.get("center_x", 0.5)) * width
    cy = float(props.get("center_y", 0.5)) * height
    radius = float(props.get("radius", 0.5)) * max(width, height)
    if radius <= 0:
        radius = 1.0

    result = Image.new("RGBA", (width, height))
    pixels = result.load()
    if pixels is None:
        return result

    for y in range(height):
        for x in range(width):
            dist = math.hypot(x - cx, y - cy)
            t = min(1.0, dist / radius)
            r = round(center_color[0] + (outer_color[0] - center_color[0]) * t)
            g = round(center_color[1] + (outer_color[1] - center_color[1]) * t)
            b = round(center_color[2] + (outer_color[2] - center_color[2]) * t)
            a = round((center_opacity + (outer_opacity - center_opacity) * t) * 255)
            pixels[x, y] = (r, g, b, a)

    return result


def _parse_color(value: object, field: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise GradientError(f"Gradient {field} must be a hex color string.")
    try:
        rgb = ImageColor.getrgb(value)
    except (TypeError, ValueError) as exc:
        raise GradientError(f"Gradient {field} color is invalid: {value!r}.") from exc
    return (rgb[0], rgb[1], rgb[2])


def gradient_from_bytes(content: bytes) -> Image.Image:
    """Open an RGBA image from PNG bytes for gradient processing."""
    with Image.open(BytesIO(content)) as src:
        src.load()
        return src.convert("RGBA")


__all__ = [
    "GradientError",
    "apply_gradient_to_image",
    "gradient_from_bytes",
]
