"""Affine geometry helpers for WYSIWYG object transforms."""

from __future__ import annotations

import math
from dataclasses import dataclass

from batikcraft_studio.domain import LayerObject

SHEAR_X_KEY = "geometry_shear_x"
SHEAR_Y_KEY = "geometry_shear_y"
MAX_ABS_SHEAR = 4.0
MIN_ABS_SCALE = 0.01


@dataclass(frozen=True, slots=True)
class AffineHandles:
    """Canvas/project-space geometry for one selected object."""

    corners: tuple[tuple[float, float], ...]
    edge_midpoints: tuple[tuple[float, float], ...]
    rotation: tuple[float, float]
    shear_x: tuple[float, float]
    shear_y: tuple[float, float]
    center: tuple[float, float]


def object_shear(item: LayerObject) -> tuple[float, float]:
    return (_finite_property(item, SHEAR_X_KEY), _finite_property(item, SHEAR_Y_KEY))


def object_linear_matrix(item: LayerObject) -> tuple[float, float, float, float]:
    """Return local-to-world 2x2 matrix for scale/flip, shear, then rotation."""

    shear_x, shear_y = object_shear(item)
    transform = item.transform
    angle = math.radians(transform.rotation_degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    local_a = transform.scale_x
    local_b = shear_x * transform.scale_y
    local_c = shear_y * transform.scale_x
    local_d = transform.scale_y
    return (
        cos_a * local_a - sin_a * local_c,
        cos_a * local_b - sin_a * local_d,
        sin_a * local_a + cos_a * local_c,
        sin_a * local_b + cos_a * local_d,
    )


def transform_local_point(
    item: LayerObject,
    local_x: float,
    local_y: float,
) -> tuple[float, float]:
    a, b, c, d = object_linear_matrix(item)
    return (
        item.transform.x + a * local_x + b * local_y,
        item.transform.y + c * local_x + d * local_y,
    )


def inverse_transform_point(
    item: LayerObject,
    world_x: float,
    world_y: float,
) -> tuple[float, float] | None:
    a, b, c, d = object_linear_matrix(item)
    determinant = a * d - b * c
    if abs(determinant) < 1e-9:
        return None
    delta_x = world_x - item.transform.x
    delta_y = world_y - item.transform.y
    return (
        (d * delta_x - b * delta_y) / determinant,
        (-c * delta_x + a * delta_y) / determinant,
    )


def object_corners(item: LayerObject) -> tuple[tuple[float, float], ...]:
    half_width = item.bounds.width / 2
    half_height = item.bounds.height / 2
    return tuple(
        transform_local_point(item, x, y)
        for x, y in (
            (-half_width, -half_height),
            (half_width, -half_height),
            (half_width, half_height),
            (-half_width, half_height),
        )
    )


def object_affine_handles(item: LayerObject, offset: float = 28.0) -> AffineHandles:
    corners = object_corners(item)
    edges = tuple(_midpoint(corners[i], corners[(i + 1) % 4]) for i in range(4))
    center = (item.transform.x, item.transform.y)
    return AffineHandles(
        corners=corners,
        edge_midpoints=edges,
        rotation=_offset_away(edges[0], center, offset),
        shear_x=_offset_away(edges[2], center, offset * 0.72),
        shear_y=_offset_away(edges[1], center, offset * 0.72),
        center=center,
    )


def object_axis_aligned_bounds(item: LayerObject) -> tuple[float, float, float, float]:
    corners = object_corners(item)
    return (
        min(point[0] for point in corners),
        min(point[1] for point in corners),
        max(point[0] for point in corners),
        max(point[1] for point in corners),
    )


def point_hits_affine_object(item: LayerObject, x: float, y: float) -> bool:
    local = inverse_transform_point(item, x, y)
    if local is None:
        return False
    return (
        abs(local[0]) <= item.bounds.width / 2
        and abs(local[1]) <= item.bounds.height / 2
    )


def clamp_shear(value: float) -> float:
    return max(-MAX_ABS_SHEAR, min(MAX_ABS_SHEAR, float(value)))


def safe_scale(value: float, fallback_sign: float = 1.0) -> float:
    numeric = float(value)
    if abs(numeric) >= MIN_ABS_SCALE:
        return numeric
    sign = -1.0 if numeric < 0 or fallback_sign < 0 else 1.0
    return sign * MIN_ABS_SCALE


def _finite_property(item: LayerObject, key: str) -> float:
    value = item.properties.get(key, 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    numeric = float(value)
    return numeric if math.isfinite(numeric) else 0.0


def _midpoint(
    first: tuple[float, float],
    second: tuple[float, float],
) -> tuple[float, float]:
    return ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)


def _offset_away(
    point: tuple[float, float],
    center: tuple[float, float],
    distance: float,
) -> tuple[float, float]:
    delta_x = point[0] - center[0]
    delta_y = point[1] - center[1]
    length = math.hypot(delta_x, delta_y) or 1.0
    return (
        point[0] + delta_x / length * distance,
        point[1] + delta_y / length * distance,
    )


__all__ = [
    "AffineHandles",
    "MAX_ABS_SHEAR",
    "MIN_ABS_SCALE",
    "SHEAR_X_KEY",
    "SHEAR_Y_KEY",
    "clamp_shear",
    "inverse_transform_point",
    "object_affine_handles",
    "object_axis_aligned_bounds",
    "object_corners",
    "object_linear_matrix",
    "object_shear",
    "point_hits_affine_object",
    "safe_scale",
    "transform_local_point",
]
