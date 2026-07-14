"""Offline professional icons for the native Tkinter interface.

Selected Font Awesome Free 7.3.0 masks are embedded as compressed Base85 text.
Small BatikCraft-specific geometry icons are generated locally with Pillow so all
editor controls remain crisp, colored, and completely offline.
"""

from __future__ import annotations

import base64
import hashlib
import math
import zlib
from functools import cache
from types import MappingProxyType
from typing import Any

from PIL import Image, ImageColor, ImageDraw, ImageTk

from .fontawesome_assets import (
    FONT_AWESOME_LICENSE,
    FONT_AWESOME_SOURCE,
    FONT_AWESOME_VERSION,
    ICON_ALPHA_B85,
    ICON_DATA_SHA256,
    MASTER_ICON_SIZE,
)

_MIN_ICON_SIZE = 12
_FONT_AWESOME_NAMES = tuple(ICON_ALPHA_B85)
_CUSTOM_ICON_NAMES = (
    "layer_add",
    "line_tool",
    "rectangle_tool",
    "ellipse_tool",
    "polygon_tool",
    "canting_tool",
    "brush_tool",
    "pencil_tool",
    "eraser_tool",
    "motif_tool",
    "isen_tool",
)

_ICON_COLORS: dict[str, str] = {
    "new": "#7C3AED",
    "open": "#B45309",
    "save": "#2563EB",
    "import": "#0284C7",
    "undo": "#475569",
    "redo": "#0F766E",
    "duplicate": "#059669",
    "delete": "#DC2626",
    "dashboard": "#D97706",
    "editor": "#0369A1",
    "batikification": "#7C3AED",
    "preview": "#0F766E",
    "publish": "#2563EB",
    "visibility": "#2563EB",
    "lock": "#D97706",
    "up": "#15803D",
    "down": "#C2410C",
    "apply": "#16A34A",
    "select": "#4F46E5",
    "layer_add": "#2563EB",
    "line_tool": "#0F766E",
    "rectangle_tool": "#7C3AED",
    "ellipse_tool": "#0284C7",
    "polygon_tool": "#D97706",
    "canting_tool": "#7A3E2A",
    "brush_tool": "#B45309",
    "pencil_tool": "#475569",
    "eraser_tool": "#DC2626",
    "motif_tool": "#7C3AED",
    "isen_tool": "#0F766E",
}

_RAIL_ICON_COLORS: dict[str, str] = {
    "dashboard": "#FBBF24",
    "editor": "#38BDF8",
    "batikification": "#C084FC",
    "preview": "#34D399",
    "publish": "#60A5FA",
}

ICON_NAMES = tuple(_ICON_COLORS)


def available_icons() -> tuple[str, ...]:
    """Return the stable public names of all bundled and generated icons."""

    return ICON_NAMES


def default_icon_color(name: str, *, on_dark: bool = False) -> str:
    """Return the professional default color for an icon."""

    _validate_icon_name(name)
    if on_dark:
        return _RAIL_ICON_COLORS.get(name, "#F8FAFC")
    return _ICON_COLORS[name]


def font_awesome_metadata() -> MappingProxyType[str, Any]:
    """Return read-only attribution metadata for the embedded icon artwork."""

    return MappingProxyType(
        {
            "font_awesome_version": FONT_AWESOME_VERSION,
            "license": FONT_AWESOME_LICENSE,
            "source": FONT_AWESOME_SOURCE,
            "storage": "embedded-base85-alpha",
            "master_size": MASTER_ICON_SIZE,
            "icons": _FONT_AWESOME_NAMES,
            "custom_icons": _CUSTOM_ICON_NAMES,
        }
    )


def render_icon(
    name: str,
    *,
    size: int = 20,
    color: str | None = None,
) -> Image.Image:
    """Render one sharp, colored RGBA icon from an offline alpha mask."""

    _validate_icon_name(name)
    if not isinstance(size, int) or isinstance(size, bool) or size < _MIN_ICON_SIZE:
        raise ValueError(f"Icon size must be at least {_MIN_ICON_SIZE} pixels.")

    icon_color = color or default_icon_color(name)
    try:
        rgb = ImageColor.getrgb(icon_color)
        if len(rgb) != 3:
            raise ValueError
        red, green, blue = rgb
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid icon color: {icon_color!r}.") from exc

    source_alpha = _source_alpha(name)
    alpha = source_alpha.resize((size, size), Image.Resampling.LANCZOS)
    rendered = Image.new("RGBA", (size, size), (red, green, blue, 0))
    rendered.putalpha(alpha)
    return rendered


def create_icon(
    master: object,
    name: str,
    *,
    size: int = 20,
    color: str | None = None,
) -> ImageTk.PhotoImage:
    """Create a Tk-compatible offline icon."""

    return ImageTk.PhotoImage(
        render_icon(name, size=size, color=color),
        master=master,
    )


def _validate_icon_name(name: str) -> None:
    if name not in _ICON_COLORS:
        raise ValueError(f"Unknown icon: {name}")


@cache
def _decoded_alpha_masks() -> MappingProxyType[str, bytes]:
    expected_length = MASTER_ICON_SIZE * MASTER_ICON_SIZE
    decoded: dict[str, bytes] = {}
    digest = hashlib.sha256()

    if set(ICON_ALPHA_B85) != set(_FONT_AWESOME_NAMES):
        raise RuntimeError("Bundled Font Awesome icon manifest is incomplete.")

    for name in sorted(_FONT_AWESOME_NAMES):
        encoded = ICON_ALPHA_B85[name]
        try:
            compressed = base64.b85decode(encoded)
            alpha = zlib.decompress(compressed)
        except (ValueError, zlib.error) as exc:
            raise RuntimeError(f"Bundled Font Awesome icon data is corrupt: {name}.") from exc
        if len(alpha) != expected_length:
            raise RuntimeError(f"Bundled Font Awesome icon has an invalid size: {name}.")
        decoded[name] = alpha
        digest.update(alpha)

    if digest.hexdigest() != ICON_DATA_SHA256:
        raise RuntimeError("Bundled Font Awesome icon checksum failed.")
    return MappingProxyType(decoded)


@cache
def _source_alpha(name: str) -> Image.Image:
    _validate_icon_name(name)
    if name in _CUSTOM_ICON_NAMES:
        return _render_custom_alpha(name)
    return Image.frombytes(
        "L",
        (MASTER_ICON_SIZE, MASTER_ICON_SIZE),
        _decoded_alpha_masks()[name],
    )


def _render_custom_alpha(name: str) -> Image.Image:
    scale = 4
    size = MASTER_ICON_SIZE * scale
    image = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(image)
    stroke = 7
    margin = 16

    if name == "line_tool":
        draw.line((margin, size - margin, size - margin, margin), fill=255, width=stroke)
        _round_dot(draw, margin, size - margin, stroke)
        _round_dot(draw, size - margin, margin, stroke)
    elif name == "rectangle_tool":
        draw.rounded_rectangle(
            (margin, margin + 6, size - margin, size - margin - 6),
            radius=5,
            outline=255,
            width=stroke,
        )
    elif name == "ellipse_tool":
        draw.ellipse(
            (margin, margin + 6, size - margin, size - margin - 6),
            outline=255,
            width=stroke,
        )
    elif name == "polygon_tool":
        center = size / 2
        radius = size / 2 - margin
        points = [
            (
                center + math.cos(-math.pi / 2 + index * math.tau / 6) * radius,
                center + math.sin(-math.pi / 2 + index * math.tau / 6) * radius,
            )
            for index in range(6)
        ]
        draw.line((*points, points[0]), fill=255, width=stroke, joint="curve")
    elif name == "canting_tool":
        draw.line((22, 78, 67, 33), fill=255, width=12)
        draw.ellipse((50, 18, 79, 47), outline=255, width=8)
        draw.line((75, 31, 90, 20), fill=255, width=7)
        draw.line((90, 20, 93, 12), fill=255, width=5)
        draw.ellipse((15, 71, 31, 87), fill=255)
    elif name == "brush_tool":
        draw.line((23, 79, 65, 37), fill=255, width=13)
        draw.polygon(((61, 42), (77, 18), (90, 8), (84, 31), (70, 49)), fill=255)
        draw.ellipse((14, 70, 32, 88), fill=255)
    elif name == "pencil_tool":
        draw.polygon(((17, 78), (28, 88), (79, 37), (68, 26)), fill=255)
        draw.polygon(((68, 26), (79, 37), (90, 14)), fill=255)
        draw.polygon(((17, 78), (28, 88), (11, 94)), fill=255)
    elif name == "eraser_tool":
        draw.polygon(((18, 67), (50, 22), (84, 46), (52, 88)), fill=255)
        draw.line((36, 72, 69, 29), fill=0, width=5)
        draw.line((42, 82, 78, 82), fill=255, width=7)
    elif name == "motif_tool":
        center = size / 2
        for angle in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
            dx = math.cos(angle) * 22
            dy = math.sin(angle) * 22
            draw.ellipse(
                (center + dx - 17, center + dy - 17, center + dx + 17, center + dy + 17),
                outline=255,
                width=7,
            )
        draw.ellipse((center - 9, center - 9, center + 9, center + 9), fill=255)
    elif name == "isen_tool":
        for row in range(3):
            for column in range(3):
                x = 27 + column * 21
                y = 27 + row * 21
                radius = 6 if (row + column) % 2 == 0 else 4
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
        draw.rounded_rectangle((15, 15, 81, 81), radius=10, outline=255, width=5)
    else:
        draw.rounded_rectangle(
            (margin, margin + 12, size - margin - 18, size - margin),
            radius=4,
            outline=255,
            width=stroke,
        )
        center_x = size - margin - 8
        center_y = margin + 16
        draw.ellipse(
            (
                center_x - 16,
                center_y - 16,
                center_x + 16,
                center_y + 16,
            ),
            fill=255,
        )
        draw.rectangle((center_x - 3, center_y - 10, center_x + 3, center_y + 10), fill=0)
        draw.rectangle((center_x - 10, center_y - 3, center_x + 10, center_y + 3), fill=0)
        draw.rectangle((center_x - 3, center_y - 10, center_x + 3, center_y + 10), fill=255)
        draw.rectangle((center_x - 10, center_y - 3, center_x + 10, center_y + 3), fill=255)

    return image.resize(
        (MASTER_ICON_SIZE, MASTER_ICON_SIZE),
        Image.Resampling.LANCZOS,
    )


def _round_dot(draw: ImageDraw.ImageDraw, x: float, y: float, diameter: int) -> None:
    radius = diameter / 2
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
