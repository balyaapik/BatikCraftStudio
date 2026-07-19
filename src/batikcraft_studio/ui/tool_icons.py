"""Offline Font Awesome icons dedicated to the Batik tool rail and panel controls."""

from __future__ import annotations

import base64
import hashlib
import zlib
from functools import cache

from PIL import Image, ImageColor, ImageDraw, ImageTk

from .fontawesome_tool_assets import (
    TOOL_ICON_ALPHA_B85,
    TOOL_ICON_DATA_SHA256,
)

_MASTER_SIZE = 24
_M4I_CUSTOM_ICONS = frozenset(
    {"position_lock", "position_unlock", "gradient_linear", "gradient_radial", "object_opacity", "hand_tool"}
)
_DEFAULT_COLORS = {
    "select_tool": "#4F46E5",
    "hand_tool": "#0E7490",
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
    # M4I additions
    "position_lock": "#D97706",
    "position_unlock": "#16A34A",
    "gradient_linear": "#2563EB",
    "gradient_radial": "#7C3AED",
    "object_opacity": "#475569",
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
    if name in _M4I_CUSTOM_ICONS:
        return _render_m4i_alpha(name)
    try:
        raw = _decoded_masks()[name]
    except KeyError as exc:
        raise ValueError(f"Unknown tool icon: {name}") from exc
    return Image.frombytes("L", (_MASTER_SIZE, _MASTER_SIZE), raw)


def _render_m4i_alpha(name: str) -> Image.Image:
    """Generate alpha masks for M4I custom icons using Pillow geometry."""
    scale = 4
    size = _MASTER_SIZE * scale
    image = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(image)
    margin = 14

    if name == "hand_tool":
        # Telapak + empat jari + ibu jari sederhana
        palm_left, palm_right = 26, 70
        palm_top, palm_bottom = 44, 80
        draw.rounded_rectangle(
            (palm_left, palm_top, palm_right, palm_bottom), radius=12, fill=255
        )
        finger_w = 9
        for i, (fx, ftop) in enumerate(
            ((28, 20), (40, 14), (52, 16), (64, 22))
        ):
            draw.rounded_rectangle(
                (fx, ftop, fx + finger_w, palm_top + 10), radius=5, fill=255
            )
        draw.rounded_rectangle((14, 50, 30, 62), radius=6, fill=255)
        return image.resize((_MASTER_SIZE, _MASTER_SIZE), Image.Resampling.LANCZOS)

    if name == "position_lock":
        # Padlock body + shackle
        draw.rounded_rectangle((28, 44, 68, 82), radius=6, fill=255)
        draw.arc((32, 18, 64, 54), start=200, end=340, fill=255, width=8)
        draw.rectangle((44, 54, 52, 68), fill=0)
    elif name == "position_unlock":
        # Open padlock
        draw.rounded_rectangle((28, 44, 68, 82), radius=6, fill=255)
        draw.arc((32, 12, 64, 48), start=200, end=0, fill=255, width=8)
    elif name == "gradient_linear":
        # Horizontal gradient bar with arrow
        for step in range(8):
            alpha = int(30 + step * 28)
            x = 14 + step * 9
            draw.rectangle((x, 30, x + 8, 66), fill=alpha)
        draw.line((14, 76, 82, 76), fill=255, width=6)
    elif name == "gradient_radial":
        # Concentric circles
        cx, cy = size // 2, size // 2
        for r in (38, 28, 18, 8):
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=255, width=4)
        draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=255)
    elif name == "object_opacity":
        # Checkerboard + slider
        for row in range(3):
            for col in range(3):
                if (row + col) % 2 == 0:
                    x = 16 + col * 18
                    y = 16 + row * 18
                    draw.rectangle((x, y, x + 16, y + 16), fill=255)
        draw.line((20, 76, 76, 76), fill=255, width=6)
        draw.ellipse((42, 70, 54, 82), fill=255)
    else:
        # Fallback: filled square
        draw.rounded_rectangle((margin, margin, size - margin, size - margin), radius=6, fill=255)

    return image.resize((_MASTER_SIZE, _MASTER_SIZE), Image.Resampling.LANCZOS)


__all__ = ["available_tool_icons", "create_tool_icon", "render_tool_icon"]
