"""Renderer-matched affine drag calculations for the WYSIWYG editor."""

from __future__ import annotations

import math
from dataclasses import replace

from batikcraft_studio.domain import Transform
from batikcraft_studio.imaging.affine_object import clamp_shear, object_shear, safe_scale

from .wysiwyg_transform_editor import (
    WysiwygTransformEditorWorkspaceView,
    _TransformDrag,
    _unrotate_delta,
)


class PreciseTransformEditorWorkspaceView(WysiwygTransformEditorWorkspaceView):
    """Keep drag calculations identical to scale/flip → shear → rotate rendering."""

    def _dragged_geometry(
        self,
        drag: _TransformDrag,
        point: tuple[float, float],
        *,
        preserve_ratio: bool,
    ) -> tuple[Transform, float, float]:
        item = drag.original
        shear_x, shear_y = object_shear(item)
        if drag.mode == "shear_x":
            local_delta = _unrotate_delta(
                point[0] - drag.start_world[0],
                point[1] - drag.start_world[1],
                item.transform.rotation_degrees,
            )
            denominator = max(abs(item.transform.scale_y) * item.bounds.height / 2, 1e-6)
            candidate = clamp_shear(shear_x + local_delta[0] / denominator)
            return item.transform, _avoid_singular(candidate, shear_y), shear_y
        if drag.mode == "shear_y":
            local_delta = _unrotate_delta(
                point[0] - drag.start_world[0],
                point[1] - drag.start_world[1],
                item.transform.rotation_degrees,
            )
            denominator = max(abs(item.transform.scale_x) * item.bounds.width / 2, 1e-6)
            candidate = clamp_shear(shear_y + local_delta[1] / denominator)
            return item.transform, shear_x, _avoid_singular(candidate, shear_x)
        return super()._dragged_geometry(
            drag,
            point,
            preserve_ratio=preserve_ratio,
        )

    def _resize_corner(
        self,
        drag: _TransformDrag,
        point: tuple[float, float],
        preserve_ratio: bool,
        shear_x: float,
        shear_y: float,
    ) -> tuple[Transform, float, float]:
        item = drag.original
        fixed = drag.fixed_world or (item.transform.x, item.transform.y)
        local_x, local_y = _unrotate_delta(
            point[0] - fixed[0],
            point[1] - fixed[1],
            item.transform.rotation_degrees,
        )
        determinant = 1.0 - shear_x * shear_y
        if abs(determinant) < 0.05:
            determinant = math.copysign(0.05, determinant or 1.0)
        scaled_x_vector = (local_x - shear_x * local_y) / determinant
        scaled_y_vector = (-shear_y * local_x + local_y) / determinant
        scale_x = safe_scale(
            scaled_x_vector / (drag.sign_x * item.bounds.width),
            item.transform.scale_x,
        )
        scale_y = safe_scale(
            scaled_y_vector / (drag.sign_y * item.bounds.height),
            item.transform.scale_y,
        )
        if preserve_ratio:
            ratio = max(
                abs(scale_x / item.transform.scale_x),
                abs(scale_y / item.transform.scale_y),
            )
            scale_x = math.copysign(abs(item.transform.scale_x) * ratio, scale_x)
            scale_y = math.copysign(abs(item.transform.scale_y) * ratio, scale_y)
        center_x = (fixed[0] + point[0]) / 2
        center_y = (fixed[1] + point[1]) / 2
        return (
            replace(
                item.transform,
                x=center_x,
                y=center_y,
                scale_x=scale_x,
                scale_y=scale_y,
            ),
            shear_x,
            shear_y,
        )


def _avoid_singular(candidate: float, other_axis: float) -> float:
    if not other_axis:
        return candidate
    determinant = 1.0 - candidate * other_axis
    if abs(determinant) >= 0.05:
        return candidate
    boundary = (1.0 - math.copysign(0.05, determinant or 1.0)) / other_axis
    return clamp_shear(boundary)


__all__ = ["PreciseTransformEditorWorkspaceView"]
