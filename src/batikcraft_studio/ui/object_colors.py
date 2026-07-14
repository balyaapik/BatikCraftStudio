"""Resolve primary and secondary palette colors from selected editor content."""

from __future__ import annotations

import re
from collections import Counter
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from batikcraft_studio.domain import Layer, LayerObject, ObjectKind

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def declared_object_colors(item: LayerObject) -> tuple[str | None, str | None]:
    """Return semantic primary/secondary colors stored by an editable object."""

    properties = item.properties
    if item.kind is ObjectKind.MOTIF:
        return (
            _property_color(properties, "warna_motif", "motif_color", "stroke_color"),
            _property_color(properties, "warna_isen", "isen_color", "fill_color"),
        )
    if item.kind is ObjectKind.ISEN:
        return (_property_color(properties, "warna_isen", "isen_color"), None)
    if item.kind is ObjectKind.PAINT_STROKE:
        return (_property_color(properties, "brush_color", "stroke_color"), None)
    if item.kind is ObjectKind.SHAPE:
        return (
            _property_color(properties, "stroke_color", "brush_color"),
            _property_color(properties, "fill_color"),
        )
    return (
        _property_color(
            properties,
            "brush_color",
            "stroke_color",
            "warna_motif",
            "warna_isen",
            "color",
        ),
        _property_color(properties, "fill_color", "warna_isen"),
    )


def declared_layer_colors(layer: Layer) -> tuple[str | None, str | None]:
    """Return colors from legacy shape/paint layers when no object is selected."""

    return (
        _property_color(
            layer.properties,
            "brush_color",
            "stroke_color",
            "warna_motif",
            "warna_isen",
            "color",
        ),
        _property_color(layer.properties, "fill_color", "warna_isen"),
    )


def dominant_raster_colors(
    content: bytes,
    *,
    canvas_color: str = "#FFFFFF",
) -> tuple[str | None, str | None]:
    """Estimate two useful opaque colors from a raster asset.

    Pixels are grouped into compact RGB bins so this stays fast for large asset
    libraries. Transparent pixels are ignored. A canvas-like background is deprioritized
    when other colors are available.
    """

    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            image = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError):
        return (None, None)

    image.thumbnail((112, 112), Image.Resampling.LANCZOS)
    counts: Counter[tuple[int, int, int]] = Counter()
    for red, green, blue, alpha in image.getdata():
        if alpha < 40:
            continue
        counts[(_bin(red), _bin(green), _bin(blue))] += max(1, alpha // 48)
    if not counts:
        return (None, None)

    canvas_rgb = _hex_rgb(canvas_color) or (255, 255, 255)
    ranked = [color for color, _count in counts.most_common(12)]
    non_canvas = [color for color in ranked if _distance(color, canvas_rgb) >= 28]
    candidates = non_canvas or ranked

    primary = candidates[0]
    secondary = next(
        (color for color in candidates[1:] if _distance(color, primary) >= 45),
        None,
    )
    return (_rgb_hex(primary), _rgb_hex(secondary) if secondary is not None else None)


def _property_color(properties: object, *keys: str) -> str | None:
    if not hasattr(properties, "get"):
        return None
    for key in keys:
        value = properties.get(key)  # type: ignore[union-attr]
        if isinstance(value, str) and _HEX_COLOR.fullmatch(value.strip()):
            return value.strip().upper()
    return None


def _bin(value: int) -> int:
    return min(255, (value // 16) * 16 + 8)


def _hex_rgb(value: str) -> tuple[int, int, int] | None:
    if not isinstance(value, str) or not _HEX_COLOR.fullmatch(value.strip()):
        return None
    normalized = value.strip().lstrip("#")
    return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _rgb_hex(color: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*color)


def _distance(
    first: tuple[int, int, int],
    second: tuple[int, int, int],
) -> float:
    return sum((left - right) ** 2 for left, right in zip(first, second, strict=True)) ** 0.5


__all__ = [
    "declared_layer_colors",
    "declared_object_colors",
    "dominant_raster_colors",
]
