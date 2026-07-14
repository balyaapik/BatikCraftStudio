"""Pure geometry for canvas resize, rotation, and shear handles."""

from __future__ import annotations

import math
from dataclasses import dataclass

from batikcraft_studio.domain import LayerObject, Transform
from batikcraft_studio.imaging import object_shear, transformed_object_corners

Point = tuple[float, float]
_HANDLE_RADIUS = 8.0
_ROTATION_OFFSET = 34.0
_SHEAR_OFFSET = 17.0
_MIN_SCALE = 1e-3


@dataclass(frozen=True, slots=True)
class GizmoGeometry:
    corners: tuple[Point, Point, Point, Point]
    scale_handles: dict[str, Point]
    shear_handles: dict[str, Point]
    rotation_handle: Point
    rotation_anchor: Point
    center: Point


@dataclass(frozen=True, slots=True)
class TransformPreview:
    transform: Transform
    shear_x: float
    shear_y: float


def build_gizmo_geometry(
    item: LayerObject,
    *,
    preview_left: float,
    preview_top: float,
    preview_scale: float,
) -> GizmoGeometry:
    project_corners = transformed_object_corners(item, preview_scale=preview_scale)
    corners = tuple(
        (preview_left + point[0], preview_top + point[1])
        for point in project_corners
    )
    northwest, northeast, southeast, southwest = corners
    north = _midpoint(northwest, northeast)
    east = _midpoint(northeast, southeast)
    south = _midpoint(southwest, southeast)
    west = _midpoint(northwest, southwest)
    center = (
        preview_left + item.transform.x * preview_scale,
        preview_top + item.transform.y * preview_scale,
    )
    north_out = _unit_vector(center, north)
    east_out = _unit_vector(center, east)
    south_out = _unit_vector(center, south)
    west_out = _unit_vector(center, west)
    return GizmoGeometry(
        corners=(northwest, northeast, southeast, southwest),
        scale_handles={
            "scale-nw": northwest,
            "scale-n": north,
            "scale-ne": northeast,
            "scale-e": east,
            "scale-se": southeast,
            "scale-s": south,
            "scale-sw": southwest,
            "scale-w": west,
        },
        shear_handles={
            "shear-n": _offset(north, north_out, _SHEAR_OFFSET),
            "shear-e": _offset(east, east_out, _SHEAR_OFFSET),
            "shear-s": _offset(south, south_out, _SHEAR_OFFSET),
            "shear-w": _offset(west, west_out, _SHEAR_OFFSET),
        },
        rotation_handle=_offset(north, north_out, _ROTATION_OFFSET),
        rotation_anchor=north,
        center=center,
    )


def hit_test_gizmo(geometry: GizmoGeometry, x: float, y: float) -> str | None:
    """Return the topmost handle under one canvas point."""

    if _distance((x, y), geometry.rotation_handle) <= _HANDLE_RADIUS + 2:
        return "rotate"
    for key, point in geometry.shear_handles.items():
        if _distance((x, y), point) <= _HANDLE_RADIUS:
            return key
    for key, point in geometry.scale_handles.items():
        if _distance((x, y), point) <= _HANDLE_RADIUS:
            return key
    return None


def move_preview(
    start: TransformPreview,
    *,
    delta_x: float,
    delta_y: float,
) -> TransformPreview:
    return TransformPreview(
        transform=Transform(
            x=start.transform.x + delta_x,
            y=start.transform.y + delta_y,
            rotation_degrees=start.transform.rotation_degrees,
            scale_x=start.transform.scale_x,
            scale_y=start.transform.scale_y,
        ),
        shear_x=start.shear_x,
        shear_y=start.shear_y,
    )


def rotation_preview(
    start: TransformPreview,
    *,
    center: Point,
    start_pointer: Point,
    pointer: Point,
    snap: bool = False,
) -> TransformPreview:
    start_angle = math.atan2(start_pointer[1] - center[1], start_pointer[0] - center[0])
    current_angle = math.atan2(pointer[1] - center[1], pointer[0] - center[0])
    rotation = start.transform.rotation_degrees + math.degrees(current_angle - start_angle)
    if snap:
        rotation = round(rotation / 15.0) * 15.0
    return TransformPreview(
        transform=Transform(
            x=start.transform.x,
            y=start.transform.y,
            rotation_degrees=rotation,
            scale_x=start.transform.scale_x,
            scale_y=start.transform.scale_y,
        ),
        shear_x=start.shear_x,
        shear_y=start.shear_y,
    )


def scale_preview(
    start: TransformPreview,
    *,
    handle: str,
    pointer: Point,
    width: float,
    height: float,
) -> TransformPreview:
    """Resize from one handle while keeping the opposite handle anchored."""

    horizontal = handle.rsplit("-", 1)[-1]
    east = "e" in horizontal
    west = "w" in horizontal
    north = "n" in horizontal
    south = "s" in horizontal
    transform = start.transform
    shear_x = start.shear_x
    shear_y = start.shear_y

    if east or west:
        sign_x = 1.0 if east else -1.0
    else:
        sign_x = 0.0
    if south or north:
        sign_y = 1.0 if south else -1.0
    else:
        sign_y = 0.0

    opposite_local = (-sign_x * width / 2, -sign_y * height / 2)
    anchor = _transform_local(start, opposite_local)
    delta_world = (pointer[0] - anchor[0], pointer[1] - anchor[1])
    unrotated = _rotate(delta_world, -transform.rotation_degrees)

    new_scale_x = transform.scale_x
    new_scale_y = transform.scale_y
    if sign_x and sign_y:
        determinant = 1.0 - shear_x * shear_y
        first = (unrotated[0] - shear_x * unrotated[1]) / determinant
        second = (unrotated[1] - shear_y * unrotated[0]) / determinant
        new_scale_x = _nonzero(first / (sign_x * width))
        new_scale_y = _nonzero(second / (sign_y * height))
    elif sign_x:
        denominator = 1.0 + shear_y * shear_y
        first = (unrotated[0] + shear_y * unrotated[1]) / denominator
        new_scale_x = _nonzero(first / (sign_x * width))
    elif sign_y:
        denominator = 1.0 + shear_x * shear_x
        second = (shear_x * unrotated[0] + unrotated[1]) / denominator
        new_scale_y = _nonzero(second / (sign_y * height))

    candidate = TransformPreview(
        transform=Transform(
            x=transform.x,
            y=transform.y,
            rotation_degrees=transform.rotation_degrees,
            scale_x=new_scale_x,
            scale_y=new_scale_y,
        ),
        shear_x=shear_x,
        shear_y=shear_y,
    )
    dragged_local = (sign_x * width / 2, sign_y * height / 2)
    constrained_pointer = _transform_local(candidate, dragged_local)
    center = _midpoint(anchor, constrained_pointer)
    return TransformPreview(
        transform=Transform(
            x=center[0],
            y=center[1],
            rotation_degrees=transform.rotation_degrees,
            scale_x=new_scale_x,
            scale_y=new_scale_y,
        ),
        shear_x=shear_x,
        shear_y=shear_y,
    )


def shear_preview(
    start: TransformPreview,
    *,
    handle: str,
    start_pointer: Point,
    pointer: Point,
    width: float,
    height: float,
) -> TransformPreview:
    delta = (pointer[0] - start_pointer[0], pointer[1] - start_pointer[1])
    unrotated = _rotate(delta, -start.transform.rotation_degrees)
    shear_x = start.shear_x
    shear_y = start.shear_y
    if handle in {"shear-n", "shear-s"}:
        sign = -1.0 if handle.endswith("n") else 1.0
        denominator = start.transform.scale_y * sign * height / 2
        if abs(denominator) > 1e-9:
            shear_x += unrotated[0] / denominator
    else:
        sign = -1.0 if handle.endswith("w") else 1.0
        denominator = start.transform.scale_x * sign * width / 2
        if abs(denominator) > 1e-9:
            shear_y += unrotated[1] / denominator
    return TransformPreview(start.transform, shear_x, shear_y)


def preview_from_item(item: LayerObject) -> TransformPreview:
    shear_x, shear_y = object_shear(item)
    return TransformPreview(item.transform, shear_x, shear_y)


def _transform_local(preview: TransformPreview, point: Point) -> Point:
    x, y = point
    sx = preview.transform.scale_x
    sy = preview.transform.scale_y
    sheared = (
        sx * x + preview.shear_x * sy * y,
        preview.shear_y * sx * x + sy * y,
    )
    rotated = _rotate(sheared, preview.transform.rotation_degrees)
    return (
        preview.transform.x + rotated[0],
        preview.transform.y + rotated[1],
    )


def _rotate(point: Point, degrees: float) -> Point:
    angle = math.radians(degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return (
        cosine * point[0] - sine * point[1],
        sine * point[0] + cosine * point[1],
    )


def _nonzero(value: float) -> float:
    if abs(value) >= _MIN_SCALE:
        return value
    return _MIN_SCALE if value >= 0 else -_MIN_SCALE


def _midpoint(first: Point, second: Point) -> Point:
    return ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)


def _unit_vector(origin: Point, target: Point) -> Point:
    delta = (target[0] - origin[0], target[1] - origin[1])
    length = math.hypot(*delta)
    return (0.0, -1.0) if length <= 1e-9 else (delta[0] / length, delta[1] / length)


def _offset(point: Point, direction: Point, distance: float) -> Point:
    return (point[0] + direction[0] * distance, point[1] + direction[1] * distance)


def _distance(first: Point, second: Point) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


__all__ = [
    "GizmoGeometry",
    "TransformPreview",
    "build_gizmo_geometry",
    "hit_test_gizmo",
    "move_preview",
    "preview_from_item",
    "rotation_preview",
    "scale_preview",
    "shear_preview",
]
