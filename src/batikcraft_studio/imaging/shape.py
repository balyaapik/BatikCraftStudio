"""Validated non-destructive shape geometry and Pillow rendering."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageColor, ImageDraw

from batikcraft_studio.domain import Layer, LayerKind

SHAPE_TYPES = ("line", "rectangle", "ellipse", "polygon")
MAX_POLYGON_SIDES = 12
MIN_POLYGON_SIDES = 3
MAX_SHAPE_STROKE_WIDTH = 1024.0


class ShapeError(ValueError):
    """Raised when shape geometry or style is invalid."""


@dataclass(frozen=True, slots=True)
class ShapeGeometry:
    """Resolved project-space shape bounds and serializable properties."""

    center_x: float
    center_y: float
    properties: Mapping[str, Any]


def build_shape_geometry(
    shape_type: str,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    stroke_color: str = "#273043",
    fill_color: str = "#D9A566",
    stroke_width: float = 4.0,
    stroke_enabled: bool = True,
    fill_enabled: bool = True,
    polygon_sides: int = 6,
    constrain: bool = False,
    from_center: bool = False,
) -> ShapeGeometry:
    """Build validated shape properties from a pointer drag."""

    kind = _validate_shape_type(shape_type)
    start_x, start_y = _validate_point(start, "start")
    end_x, end_y = _validate_point(end, "end")
    if not isinstance(constrain, bool) or not isinstance(from_center, bool):
        raise ShapeError("Shape modifiers must be booleans.")

    end_x, end_y = _apply_constraint(kind, start_x, start_y, end_x, end_y, constrain)
    if from_center:
        left = start_x - abs(end_x - start_x)
        right = start_x + abs(end_x - start_x)
        top = start_y - abs(end_y - start_y)
        bottom = start_y + abs(end_y - start_y)
        line_start = (left, top)
        line_end = (right, bottom)
    else:
        left, right = sorted((start_x, end_x))
        top, bottom = sorted((start_y, end_y))
        line_start = (start_x, start_y)
        line_end = (end_x, end_y)

    geometry_width = abs(right - left)
    geometry_height = abs(bottom - top)
    if kind != "line" and (geometry_width < 1.0 or geometry_height < 1.0):
        raise ShapeError("Shapes must be at least 1 pixel wide and high.")
    if kind == "line" and geometry_width < 1.0 and geometry_height < 1.0:
        raise ShapeError("Lines must have a visible length.")

    width = _validate_stroke_width(stroke_width)
    stroke = _validate_color(stroke_color, "stroke color")
    fill = _validate_color(fill_color, "fill color")
    stroke_on, fill_on = _validate_paint_flags(
        kind,
        stroke_enabled=stroke_enabled,
        fill_enabled=fill_enabled,
    )
    sides = _validate_polygon_sides(polygon_sides)
    padding = max(2.0, width / 2 + 2.0)
    pixel_width = max(1.0, geometry_width + padding * 2)
    pixel_height = max(1.0, geometry_height + padding * 2)

    line_orientation = _line_orientation(line_start, line_end)
    properties: dict[str, Any] = {
        "shape_type": kind,
        "geometry_width": geometry_width,
        "geometry_height": geometry_height,
        "pixel_width": pixel_width,
        "pixel_height": pixel_height,
        "padding": padding,
        "stroke_color": stroke,
        "fill_color": fill,
        "stroke_width": width,
        "stroke_enabled": stroke_on,
        "fill_enabled": fill_on,
        "polygon_sides": sides,
        "line_orientation": line_orientation,
    }
    return ShapeGeometry(
        center_x=(left + right) / 2,
        center_y=(top + bottom) / 2,
        properties=properties,
    )


def update_shape_properties(
    layer: Layer,
    *,
    geometry_width: float | None = None,
    geometry_height: float | None = None,
    stroke_color: str | None = None,
    fill_color: str | None = None,
    stroke_width: float | None = None,
    stroke_enabled: bool | None = None,
    fill_enabled: bool | None = None,
    polygon_sides: int | None = None,
) -> dict[str, Any]:
    """Return validated replacement properties for an existing shape layer."""

    values = parse_shape_properties(layer)
    width = values["geometry_width"] if geometry_width is None else _positive(geometry_width, "width")
    height = (
        values["geometry_height"]
        if geometry_height is None
        else _positive(geometry_height, "height")
    )
    line = values["shape_type"] == "line"
    if line:
        width = max(0.0, width)
        height = max(0.0, height)
        if width < 1.0 and height < 1.0:
            raise ShapeError("Lines must have a visible length.")
    elif width < 1.0 or height < 1.0:
        raise ShapeError("Shapes must be at least 1 pixel wide and high.")

    new_stroke_width = (
        values["stroke_width"]
        if stroke_width is None
        else _validate_stroke_width(stroke_width)
    )
    new_stroke_enabled = (
        values["stroke_enabled"] if stroke_enabled is None else stroke_enabled
    )
    new_fill_enabled = values["fill_enabled"] if fill_enabled is None else fill_enabled
    stroke_on, fill_on = _validate_paint_flags(
        values["shape_type"],
        stroke_enabled=new_stroke_enabled,
        fill_enabled=new_fill_enabled,
    )
    padding = max(2.0, new_stroke_width / 2 + 2.0)
    updated = dict(layer.properties)
    updated.update(
        {
            "geometry_width": width,
            "geometry_height": height,
            "pixel_width": max(1.0, width + padding * 2),
            "pixel_height": max(1.0, height + padding * 2),
            "padding": padding,
            "stroke_color": values["stroke_color"]
            if stroke_color is None
            else _validate_color(stroke_color, "stroke color"),
            "fill_color": values["fill_color"]
            if fill_color is None
            else _validate_color(fill_color, "fill color"),
            "stroke_width": new_stroke_width,
            "stroke_enabled": stroke_on,
            "fill_enabled": fill_on,
            "polygon_sides": values["polygon_sides"]
            if polygon_sides is None
            else _validate_polygon_sides(polygon_sides),
        }
    )
    return updated


def parse_shape_properties(layer: Layer) -> dict[str, Any]:
    """Validate and normalize properties from a shape layer."""

    if layer.kind is not LayerKind.SHAPE:
        raise ShapeError("Layer is not a shape layer.")
    properties = layer.properties
    kind = _validate_shape_type(properties.get("shape_type"))
    geometry_width = _non_negative(properties.get("geometry_width"), "geometry width")
    geometry_height = _non_negative(properties.get("geometry_height"), "geometry height")
    if kind != "line" and (geometry_width < 1.0 or geometry_height < 1.0):
        raise ShapeError("Shape geometry must be at least 1 pixel wide and high.")
    if kind == "line" and geometry_width < 1.0 and geometry_height < 1.0:
        raise ShapeError("Line geometry must have a visible length.")

    stroke_enabled, fill_enabled = _validate_paint_flags(
        kind,
        stroke_enabled=properties.get("stroke_enabled"),
        fill_enabled=properties.get("fill_enabled"),
    )
    return {
        "shape_type": kind,
        "geometry_width": geometry_width,
        "geometry_height": geometry_height,
        "pixel_width": _positive(properties.get("pixel_width"), "pixel width"),
        "pixel_height": _positive(properties.get("pixel_height"), "pixel height"),
        "padding": _positive(properties.get("padding"), "padding"),
        "stroke_color": _validate_color(properties.get("stroke_color"), "stroke color"),
        "fill_color": _validate_color(properties.get("fill_color"), "fill color"),
        "stroke_width": _validate_stroke_width(properties.get("stroke_width")),
        "stroke_enabled": stroke_enabled,
        "fill_enabled": fill_enabled,
        "polygon_sides": _validate_polygon_sides(properties.get("polygon_sides")),
        "line_orientation": _validate_line_orientation(properties.get("line_orientation")),
    }


def render_shape_image(layer: Layer, width: int, height: int) -> Image.Image:
    """Render one shape layer into an antialiased transparent RGBA image."""

    if width < 1 or height < 1:
        raise ShapeError("Rendered shape dimensions must be positive.")
    values = parse_shape_properties(layer)
    supersample = 4 if max(width, height) <= 2048 else 2
    output_size = (width * supersample, height * supersample)
    image = Image.new("RGBA", output_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    scale_x = width / values["pixel_width"] * supersample
    scale_y = height / values["pixel_height"] * supersample
    padding_x = values["padding"] * scale_x
    padding_y = values["padding"] * scale_y
    bounds = (
        padding_x,
        padding_y,
        output_size[0] - padding_x,
        output_size[1] - padding_y,
    )
    stroke_width = max(
        1,
        round(values["stroke_width"] * min(scale_x, scale_y)),
    )
    stroke = values["stroke_color"] if values["stroke_enabled"] else None
    fill = values["fill_color"] if values["fill_enabled"] else None

    if values["shape_type"] == "line":
        start, end = _rendered_line_points(bounds, values["line_orientation"])
        draw.line((start, end), fill=values["stroke_color"], width=stroke_width)
    elif values["shape_type"] == "rectangle":
        draw.rectangle(bounds, fill=fill, outline=stroke, width=stroke_width)
    elif values["shape_type"] == "ellipse":
        draw.ellipse(bounds, fill=fill, outline=stroke, width=stroke_width)
    else:
        points = _regular_polygon_points(bounds, values["polygon_sides"])
        draw.polygon(points, fill=fill)
        if stroke is not None:
            draw.line((*points, points[0]), fill=stroke, width=stroke_width, joint="curve")

    return image.resize((width, height), Image.Resampling.LANCZOS)


def _apply_constraint(
    shape_type: str,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    constrain: bool,
) -> tuple[float, float]:
    if not constrain:
        return end_x, end_y
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    if shape_type == "line":
        distance = math.hypot(delta_x, delta_y)
        if distance == 0:
            return end_x, end_y
        angle = round(math.atan2(delta_y, delta_x) / (math.pi / 4)) * (math.pi / 4)
        return start_x + math.cos(angle) * distance, start_y + math.sin(angle) * distance
    size = max(abs(delta_x), abs(delta_y))
    return (
        start_x + math.copysign(size, delta_x or 1.0),
        start_y + math.copysign(size, delta_y or 1.0),
    )


def _line_orientation(
    start: tuple[float, float],
    end: tuple[float, float],
) -> str:
    horizontal = "right" if end[0] >= start[0] else "left"
    vertical = "down" if end[1] >= start[1] else "up"
    return f"{horizontal}_{vertical}"


def _rendered_line_points(
    bounds: tuple[float, float, float, float],
    orientation: str,
) -> tuple[tuple[float, float], tuple[float, float]]:
    left, top, right, bottom = bounds
    if orientation == "right_down":
        return (left, top), (right, bottom)
    if orientation == "right_up":
        return (left, bottom), (right, top)
    if orientation == "left_down":
        return (right, top), (left, bottom)
    return (right, bottom), (left, top)


def _regular_polygon_points(
    bounds: tuple[float, float, float, float],
    sides: int,
) -> list[tuple[float, float]]:
    left, top, right, bottom = bounds
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    radius_x = max(0.5, (right - left) / 2)
    radius_y = max(0.5, (bottom - top) / 2)
    return [
        (
            center_x + math.cos(-math.pi / 2 + index * math.tau / sides) * radius_x,
            center_y + math.sin(-math.pi / 2 + index * math.tau / sides) * radius_y,
        )
        for index in range(sides)
    ]


def _validate_shape_type(value: object) -> str:
    if not isinstance(value, str) or value not in SHAPE_TYPES:
        raise ShapeError(f"Shape type must be one of: {', '.join(SHAPE_TYPES)}.")
    return value


def _validate_point(value: object, label: str) -> tuple[float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ShapeError(f"Shape {label} must contain x and y coordinates.")
    x = _finite(value[0], f"{label} x")
    y = _finite(value[1], f"{label} y")
    return x, y


def _validate_color(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ShapeError(f"Shape {label} must be a color string.")
    try:
        red, green, blue = ImageColor.getrgb(value)[:3]
    except (TypeError, ValueError) as exc:
        raise ShapeError(f"Shape {label} is invalid.") from exc
    return f"#{red:02X}{green:02X}{blue:02X}"


def _validate_stroke_width(value: object) -> float:
    width = _finite(value, "stroke width")
    if not 0.5 <= width <= MAX_SHAPE_STROKE_WIDTH:
        raise ShapeError(
            f"Shape stroke width must be between 0.5 and {MAX_SHAPE_STROKE_WIDTH:g}."
        )
    return width


def _validate_polygon_sides(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ShapeError("Polygon sides must be an integer.")
    if not MIN_POLYGON_SIDES <= value <= MAX_POLYGON_SIDES:
        raise ShapeError(
            f"Polygon sides must be between {MIN_POLYGON_SIDES} and {MAX_POLYGON_SIDES}."
        )
    return value


def _validate_paint_flags(
    shape_type: str,
    *,
    stroke_enabled: object,
    fill_enabled: object,
) -> tuple[bool, bool]:
    if not isinstance(stroke_enabled, bool) or not isinstance(fill_enabled, bool):
        raise ShapeError("Shape fill and stroke flags must be booleans.")
    if shape_type == "line":
        if not stroke_enabled:
            raise ShapeError("Line shapes require an enabled stroke.")
        return True, False
    if not stroke_enabled and not fill_enabled:
        raise ShapeError("A shape must have fill, stroke, or both enabled.")
    return stroke_enabled, fill_enabled


def _validate_line_orientation(value: object) -> str:
    allowed = {"right_down", "right_up", "left_down", "left_up"}
    if not isinstance(value, str) or value not in allowed:
        raise ShapeError("Line orientation is invalid.")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ShapeError(f"Shape {label} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ShapeError(f"Shape {label} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ShapeError(f"Shape {label} must be a finite number.")
    return number


def _positive(value: object, label: str) -> float:
    number = _finite(value, label)
    if number <= 0:
        raise ShapeError(f"Shape {label} must be positive.")
    return number


def _non_negative(value: object, label: str) -> float:
    number = _finite(value, label)
    if number < 0:
        raise ShapeError(f"Shape {label} must not be negative.")
    return number
