"""Non-destructive, Pillow-vectorized gradient compositing.

Gradients are stored in ``LayerObject.properties`` and are applied at render
time. The source alpha is multiplied by gradient-stop alpha, so transparent
stops remain effective without changing the original object geometry.
"""

from __future__ import annotations

import math
from io import BytesIO
from typing import Any

from PIL import Image, ImageChops, ImageColor, ImageOps


class GradientError(ValueError):
    """Raised when gradient properties contain invalid values."""


def apply_gradient_to_image(
    image: Image.Image,
    gradient: dict[str, Any],
    fill_mode: str,
) -> Image.Image:
    """Apply a linear or radial gradient while preserving source transparency."""

    source = image.convert("RGBA")
    width, height = source.size
    if fill_mode == "linear_gradient":
        gradient_image = _build_linear_gradient(width, height, gradient)
    elif fill_mode == "radial_gradient":
        gradient_image = _build_radial_gradient(width, height, gradient)
    else:
        return source

    source_alpha = source.getchannel("A")
    stop_alpha = gradient_image.getchannel("A")
    gradient_image.putalpha(ImageChops.multiply(source_alpha, stop_alpha))
    return gradient_image


def _build_linear_gradient(
    width: int,
    height: int,
    props: dict[str, Any],
) -> Image.Image:
    angle = float(props.get("angle", 0.0))
    start_color = _parse_color(props.get("start_color", "#000000"), "start_color")
    end_color = _parse_color(props.get("end_color", "#FFFFFF"), "end_color")
    start_opacity = _clamp01(props.get("start_opacity", 1.0))
    end_opacity = _clamp01(props.get("end_opacity", 1.0))
    offset_x = max(-1.0, min(1.0, float(props.get("offset_x", 0.0))))
    offset_y = max(-1.0, min(1.0, float(props.get("offset_y", 0.0))))

    # Build a C-level Pillow gradient on a square large enough that rotating and
    # cropping never exposes an uninitialised corner. Positive angles follow the
    # editor contract: 0° top-to-bottom and 90° left-to-right.
    diagonal = max(2, int(math.ceil(math.hypot(width, height))) * 2)
    ramp = Image.linear_gradient("L").resize(
        (diagonal, diagonal),
        Image.Resampling.BICUBIC,
    )
    rotated = ramp.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=False,
    )
    center_x = diagonal / 2 - offset_x * width
    center_y = diagonal / 2 - offset_y * height
    left = round(center_x - width / 2)
    top = round(center_y - height / 2)
    t_channel = rotated.crop((left, top, left + width, top + height))
    if t_channel.size != (width, height):
        t_channel = t_channel.resize((width, height), Image.Resampling.BICUBIC)

    # With a centred gradient, the visible object bounds represent the complete
    # start-to-end interval. Stretch the cropped projection to exact 0..255 so
    # edge pixels receive the configured stop opacities and colors.
    if abs(offset_x) < 1e-12 and abs(offset_y) < 1e-12:
        t_channel = ImageOps.autocontrast(t_channel)

    return _blend_colors_with_t(
        start_color,
        end_color,
        start_opacity,
        end_opacity,
        t_channel,
    )


def _build_radial_gradient(
    width: int,
    height: int,
    props: dict[str, Any],
) -> Image.Image:
    center_color = _parse_color(props.get("center_color", "#000000"), "center_color")
    outer_color = _parse_color(props.get("outer_color", "#FFFFFF"), "outer_color")
    center_opacity = _clamp01(props.get("center_opacity", 1.0))
    outer_opacity = _clamp01(props.get("outer_opacity", 1.0))
    center_x = max(0.0, min(1.0, float(props.get("center_x", 0.5))))
    center_y = max(0.0, min(1.0, float(props.get("center_y", 0.5))))
    radius = max(1.0, float(props.get("radius", 0.5)) * max(width, height))

    diameter = max(2, int(math.ceil(radius * 2)))
    radial = Image.radial_gradient("L").resize(
        (diameter, diameter),
        Image.Resampling.BICUBIC,
    )
    t_channel = Image.new("L", (width, height), 255)
    left = round(center_x * width - diameter / 2)
    top = round(center_y * height - diameter / 2)
    t_channel.paste(radial, (left, top))
    return _blend_colors_with_t(
        center_color,
        outer_color,
        center_opacity,
        outer_opacity,
        t_channel,
    )


def _blend_colors_with_t(
    start_color: tuple[int, int, int],
    end_color: tuple[int, int, int],
    start_opacity: float,
    end_opacity: float,
    t_channel: Image.Image,
) -> Image.Image:
    """Map one 8-bit interpolation channel into four RGBA channels in C."""

    def channel(start: int, end: int) -> Image.Image:
        lut = [round(start + (end - start) * value / 255) for value in range(256)]
        return t_channel.point(lut)

    alpha_start = round(start_opacity * 255)
    alpha_end = round(end_opacity * 255)
    return Image.merge(
        "RGBA",
        (
            channel(start_color[0], end_color[0]),
            channel(start_color[1], end_color[1]),
            channel(start_color[2], end_color[2]),
            channel(alpha_start, alpha_end),
        ),
    )


def _parse_color(value: object, field: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise GradientError(f"Gradient {field} must be a color string.")
    try:
        rgb = ImageColor.getrgb(value)
    except (TypeError, ValueError) as exc:
        raise GradientError(f"Gradient {field} color is invalid: {value!r}.") from exc
    return (rgb[0], rgb[1], rgb[2])


def _clamp01(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError) as exc:
        raise GradientError(f"Gradient opacity is invalid: {value!r}.") from exc


def gradient_from_bytes(content: bytes) -> Image.Image:
    """Decode an RGBA image used by gradient-related tests and tools."""

    with Image.open(BytesIO(content)) as source:
        source.load()
        return source.convert("RGBA")


__all__ = [
    "GradientError",
    "apply_gradient_to_image",
    "gradient_from_bytes",
]
