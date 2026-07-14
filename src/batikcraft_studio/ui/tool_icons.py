"""Offline Font Awesome icons dedicated to the Batik tool rail and panel controls."""

from __future__ import annotations

import base64
import hashlib
import zlib
from functools import cache

from PIL import Image, ImageColor, ImageTk

from .fontawesome_tool_assets import (
    TOOL_ICON_ALPHA_B85,
    TOOL_ICON_DATA_SHA256,
)

_MASTER_SIZE = 24
_DEFAULT_COLORS = {
    "select_tool": "#4F46E5",
    "fill_tool": "#16A34A",
    "canting_tool": "#7A3E2A",
    "brush_tool": "#B45309",
    "pencil_tool": "#475569",
    "eraser_tool": "#DC2626",
    "line_tool": "#0F766E",
    "rectangle_tool": "#7C3AED",
    "ellipse_tool": "#0284C7",
    "polygon_tool": "#D97706",
    "motif_tool": "#7C3AED",
    "isen_tool": "#0F766E",
    "options_tool": "#475569",
    "dock_float": "#2563EB",
    "dock_tab": "#7C3AED",
    "dock_restore": "#0F766E",
}


def available_tool_icons() -> tuple[str, ...]:
    return tuple(_DEFAULT_COLORS)


def render_tool_icon(
    name: str,
    *,
    size: int = 20,
    color: str | None = None,
) -> Image.Image:
    if name not in _DEFAULT_COLORS:
        raise ValueError(f"Unknown tool icon: {name}")
    if not isinstance(size, int) or isinstance(size, bool) or size < 12:
        raise ValueError("Tool icon size must be at least 12 pixels.")
    rgb = ImageColor.getrgb(color or _DEFAULT_COLORS[name])[:3]
    alpha = _source_alpha(name).resize((size, size), Image.Resampling.LANCZOS)
    image = Image.new("RGBA", (size, size), (*rgb, 0))
    image.putalpha(alpha)
    return image


def create_tool_icon(
    master: object,
    name: str,
    *,
    size: int = 20,
    color: str | None = None,
) -> ImageTk.PhotoImage:
    return ImageTk.PhotoImage(
        render_tool_icon(name, size=size, color=color),
        master=master,
    )


@cache
def _decoded_masks() -> dict[str, bytes]:
    expected = _MASTER_SIZE * _MASTER_SIZE
    decoded: dict[str, bytes] = {}
    digest = hashlib.sha256()
    for name in sorted(TOOL_ICON_ALPHA_B85):
        try:
            content = zlib.decompress(base64.b85decode(TOOL_ICON_ALPHA_B85[name]))
        except (ValueError, zlib.error) as exc:
            raise RuntimeError(f"Offline Font Awesome tool icon is corrupt: {name}.") from exc
        if len(content) != expected:
            raise RuntimeError(f"Offline Font Awesome tool icon has invalid dimensions: {name}.")
        decoded[name] = content
        digest.update(content)
    if digest.hexdigest() != TOOL_ICON_DATA_SHA256:
        raise RuntimeError("Offline Font Awesome tool icon checksum failed.")
    return decoded


@cache
def _source_alpha(name: str) -> Image.Image:
    try:
        raw = _decoded_masks()[name]
    except KeyError as exc:
        raise ValueError(f"Unknown tool icon: {name}") from exc
    return Image.frombytes("L", (_MASTER_SIZE, _MASTER_SIZE), raw)


__all__ = ["available_tool_icons", "create_tool_icon", "render_tool_icon"]
