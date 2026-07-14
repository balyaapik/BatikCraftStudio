"""Offline Font Awesome icons for the native Tkinter interface.

Selected Font Awesome Free 7.3.0 masks are embedded as compressed Base85 text.
Rendering happens locally with Pillow; the application never downloads icons
and does not depend on an installed icon font or a binary ZIP resource.
"""

from __future__ import annotations

import base64
import hashlib
import zlib
from functools import cache
from types import MappingProxyType
from typing import Any

from PIL import Image, ImageColor, ImageTk

from .fontawesome_assets import (
    FONT_AWESOME_LICENSE,
    FONT_AWESOME_SOURCE,
    FONT_AWESOME_VERSION,
    ICON_ALPHA_B85,
    ICON_DATA_SHA256,
    MASTER_ICON_SIZE,
)

_MIN_ICON_SIZE = 12

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
    """Return the stable public names of all bundled icons."""

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
            "icons": ICON_NAMES,
        }
    )


def render_icon(
    name: str,
    *,
    size: int = 20,
    color: str | None = None,
) -> Image.Image:
    """Render one sharp, colored RGBA icon from an embedded alpha mask."""

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
    """Create a Tk-compatible offline Font Awesome icon."""

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

    if set(ICON_ALPHA_B85) != set(ICON_NAMES):
        raise RuntimeError("Bundled Font Awesome icon manifest is incomplete.")

    for name in sorted(ICON_NAMES):
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
    return Image.frombytes(
        "L",
        (MASTER_ICON_SIZE, MASTER_ICON_SIZE),
        _decoded_alpha_masks()[name],
    )
