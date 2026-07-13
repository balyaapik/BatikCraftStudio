"""Offline Font Awesome icons for the native Tkinter interface.

The bundled archive contains raster masks generated from selected Font Awesome
Free 7.3.0 SVG icons. Rendering happens locally with Pillow; the application
never downloads icons and does not depend on an installed icon font.
"""

from __future__ import annotations

import json
import zipfile
from functools import lru_cache
from importlib.resources import files
from io import BytesIO
from types import MappingProxyType
from typing import Any

from PIL import Image, ImageColor, ImageTk

FONT_AWESOME_VERSION = "7.3.0"
FONT_AWESOME_LICENSE = "CC BY 4.0"
_ARCHIVE_NAME = "fontawesome_masks.zip"
_MIN_ICON_SIZE = 12

# Restrained action colors for light toolbar surfaces.
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

# Brighter workspace colors retain contrast against the dark navigation rail.
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
    """Return read-only attribution metadata embedded with the icon archive."""

    return MappingProxyType(dict(_metadata()))


def render_icon(
    name: str,
    *,
    size: int = 20,
    color: str | None = None,
) -> Image.Image:
    """Render one sharp, colored RGBA icon from a bundled high-resolution mask."""

    _validate_icon_name(name)
    if not isinstance(size, int) or isinstance(size, bool) or size < _MIN_ICON_SIZE:
        raise ValueError(f"Icon size must be at least {_MIN_ICON_SIZE} pixels.")

    icon_color = color or default_icon_color(name)
    try:
        red, green, blue = ImageColor.getrgb(icon_color)
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


@lru_cache(maxsize=1)
def _archive_bytes() -> bytes:
    resource = files("batikcraft_studio.ui").joinpath("assets", _ARCHIVE_NAME)
    return resource.read_bytes()


@lru_cache(maxsize=1)
def _metadata() -> dict[str, Any]:
    try:
        with zipfile.ZipFile(BytesIO(_archive_bytes()), mode="r") as archive:
            data = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise RuntimeError("Bundled Font Awesome metadata is corrupt.") from exc

    if data.get("font_awesome_version") != FONT_AWESOME_VERSION:
        raise RuntimeError("Bundled Font Awesome version does not match the application.")
    if data.get("license") != FONT_AWESOME_LICENSE:
        raise RuntimeError("Bundled Font Awesome license metadata is invalid.")
    if set(data.get("icons", ())) != set(ICON_NAMES):
        raise RuntimeError("Bundled Font Awesome icon manifest is incomplete.")
    return data


@lru_cache(maxsize=None)
def _source_alpha(name: str) -> Image.Image:
    # Validate both public names and archive metadata before reading binary data.
    _validate_icon_name(name)
    _metadata()
    try:
        with zipfile.ZipFile(BytesIO(_archive_bytes()), mode="r") as archive:
            content = archive.read(f"{name}.png")
        with Image.open(BytesIO(content)) as image:
            source = image.convert("RGBA")
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise RuntimeError(f"Bundled Font Awesome icon is corrupt: {name}.") from exc

    if source.size != (256, 256):
        raise RuntimeError(f"Bundled Font Awesome icon has an invalid size: {name}.")
    return source.getchannel("A").copy()
