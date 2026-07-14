"""WYSIWYG affine transform handles for selected canvas objects."""

from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass, replace

from batikcraft_studio.application import (
    InteractiveTransformProjectSession,
    ObjectLockedError,
    ProjectSessionError,
)
from batikcraft_studio.domain import LayerNodeKind, LayerObject, ProjectValidationError, Transform
from batikcraft_studio.imaging.affine_object import (
    SHEAR_X_KEY,
    SHEAR_Y_KEY,
    clamp_shear,
    object_affine_handles,
    object_shear,
    point_hits_affine_object,
    safe_scale,
    transform_local_point,
)

from .compact_asset_editor import CompactAssetEditorWorkspaceView
from .theme import COLORS

_HANDLE_RADIUS = 6.0
_HANDLE_HIT_RADIUS = 11.0
_SHIFT_MASK = 0x0001


@dataclass(slots=True)
class _TransformDrag:
    object_id: str
    mode: str
    original: LayerObject
    start_world: tuple[float, float]
    fixed_world: tuple[float, float] | None = None
    sign_x: int = 0
    sign_y: int = 0
    start_pointer_angle: float = 0.0


class WysiwygTransformEditorWorkspaceView(CompactAssetEditorWorkspaceView):
    """Transform objects directly on canvas with live affine feedback."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._affine_drag: _TransformDrag | None = None
        self._screen_handles: dict[str, tuple[float, float]] = {}
        super().__init__(*args, **kwargs)
        self.bind_all("<Escape>", self._cancel_affine_drag, add="+")

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "select":
            super()._on_canvas_press(event)
            return
        project = self.session.project
        point = self._project_point(event.x, event.y)
        if project is None or point is None:
            return

        active = self._active_object()
        handle = self._hit_transform_handle(event.x, event.y)
        if active is not None and handle is not None:
            if active.locked or project.is_layer_effectively_locked(
                project.object_layer_id(active.object_id)
            ):
                self.set_status("Objek terkunci dan tidak dapat ditransformasi.")
                return
            self._begin_affine_drag(active, handle, point)
            return

        selected: LayerObject | None = None
        for layer in reversed(project.layers):
            if layer.node_kind is LayerNodeKind.GROUP:
                continue
            if not project.is_layer_effectively_visible(layer.layer_id):
                continue
            for item in reversed(layer.objects):
                if item.visible and point_hits_affine_object(item, *point):
                    selected = item
                    break
            if selected is not None:
                break

        if selected is None:
            super()._on_canvas_press(event)
            return

        self._transform_session.select_object(selected.object_id)
        self._refresh_layer_list()
        self._refresh_transform_fields()
        self._draw_selection()
        layer_id = project.object_layer_id(selected.object_id)
        if selected.locked or project.is_layer_effectively_locked(layer_id):
            return
        self._begin_affine_drag(selected, "move", point)

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        drag = self._affine_drag
        if drag is None:
            super()._on_canvas_drag(event)
            return
        point = self._project_point(event.x, event.y)
        if point is None:
            return
        try:
            transform, shear_x, shear_y = self._dragged_geometry(
                drag,
                point,
                preserve_ratio=bool(event.state & _SHIFT_MASK),
            )
            self._transform_session.preview_interactive_object_transform(
                drag.object_id,
                transform=transform,
                shear_x=shear_x,
                shear_y=shear_y,
            )
        except (ProjectSessionError, ProjectValidationError, ZeroDivisionError):
            return
        self._refresh_transform_fields()
        self._render()

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        if self._affine_drag is None:
            super()._on_canvas_release(event)
            return
        self._on_canvas_drag(event)
        self._transform_session.commit_interactive_object_transform()
        mode = self._affine_drag.mode
        self._affine_drag = None
        self.canvas.configure(cursor="arrow")
        self.refresh_context()
        self.set_status(self._transform_status(mode))

    def _begin_affine_drag(
        self,
        item: LayerObject,
        mode: str,
        point: tuple[float, float],
    ) -> None:
        self._transform_session.begin_interactive_object_transform(item.object_id)
        fixed_world: tuple[float, float] | None = None
        sign_x = 0
        sign_y = 0
        if mode in {"nw", "ne", "se", "sw"}:
            sign_x, sign_y = {
                "nw": (-1, -1),
                "ne": (1, -1),
                "se": (1, 1),
                "sw": (-1, 1),
            }[mode]
            fixed_world = transform_local_point(
                item,
                -sign_x * item.bounds.width / 2,
                -sign_y * item.bounds.height / 2,
            )
        elif mode in {"n", "e", "s", "w"}:
            sign_x, sign_y = {
                "n": (0, -1),
                "e": (1, 0),
                "s": (0, 1),
                "w": (-1, 0),
            }[mode]
            fixed_world = transform_local_point(
                item,
                -sign_x * item.bounds.width / 2,
                -sign_y * item.bounds.height / 2,
            )
        center = (item.transform.x, item.transform.y)
        self._affine_drag = _TransformDrag(
            object_id=item.object_id,
            mode=mode,
            original=item,
            start_world=point,
            fixed_world=fixed_world,
            sign_x=sign_x,
            sign_y=sign_y,
            start_pointer_angle=math.degrees(
                math.atan2(point[1] - center[1], point[0] - center[0])
            ),
        )
        self.canvas.configure(cursor=self._cursor_for_mode(mode))

    def _dragged_geometry(
        self,
        drag: _TransformDrag,
        point: tuple[float, float],
        *,
        preserve_ratio: bool,
    ) -> tuple[Transform, float, float]:
        item = drag.original
        transform = item.transform
        shear_x, shear_y = object_shear(item)
        mode = drag.mode
        if mode == "move":
            return (
                replace(
                    transform,
                    x=transform.x + point[0] - drag.start_world[0],
                    y=transform.y + point[1] - drag.start_world[1],
                ),
                shear_x,
                shear_y,
            )
        if mode == "rotate":
            angle = math.degrees(
                math.atan2(point[1] - transform.y, point[0] - transform.x)
            )
            rotation = transform.rotation_degrees + angle - drag.start_pointer_angle
            if preserve_ratio:
                rotation = round(rotation / 15.0) * 15.0
            return replace(transform, rotation_degrees=rotation), shear_x, shear_y
        if mode == "shear_x":
            local_delta = _unrotate_delta(
                point[0] - drag.start_world[0],
                point[1] - drag.start_world[1],
                transform.rotation_degrees,
            )
            denominator = max(abs(transform.scale_x) * item.bounds.height / 2, 1e-6)
            return transform, clamp_shear(shear_x + local_delta[0] / denominator), shear_y
        if mode == "shear_y":
            local_delta = _unrotate_delta(
                point[0] - drag.start_world[0],
                point[1] - drag.start_world[1],
                transform.rotation_degrees,
            )
            denominator = max(abs(transform.scale_y) * item.bounds.width / 2, 1e-6)
            return transform, shear_x, clamp_shear(shear_y + local_delta[1] / denominator)
        if mode in {"nw", "ne", "se", "sw"}:
            return self._resize_corner(drag, point, preserve_ratio, shear_x, shear_y)
        return self._resize_edge(drag, point, shear_x, shear_y)

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
        local_delta = _unrotate_delta(
            point[0] - fixed[0],
            point[1] - fixed[1],
            item.transform.rotation_degrees,
        )
        width_term = drag.sign_x * item.bounds.width + shear_x * drag.sign_y * item.bounds.height
        height_term = shear_y * drag.sign_x * item.bounds.width + drag.sign_y * item.bounds.height
        scale_x = safe_scale(
            local_delta[0] / width_term if abs(width_term) > 1e-9 else item.transform.scale_x,
            item.transform.scale_x,
        )
        scale_y = safe_scale(
            local_delta[1] / height_term if abs(height_term) > 1e-9 else item.transform.scale_y,
            item.transform.scale_y,
        )
        if preserve_ratio:
            ratio = max(
                abs(scale_x / item.transform.scale_x),
                abs(scale_y / item.transform.scale_y),
            )
            scale_x = math.copysign(abs(item.transform.scale_x) * ratio, scale_x)
            scale_y = math.copysign(abs(item.transform.scale_y) * ratio, scale_y)
            preview = replace(item.transform, scale_x=scale_x, scale_y=scale_y)
            temporary = replace(item, transform=preview)
            dragged = transform_local_point(
                temporary,
                drag.sign_x * item.bounds.width / 2,
                drag.sign_y * item.bounds.height / 2,
            )
            center_x = preview.x + (point[0] - dragged[0])
            center_y = preview.y + (point[1] - dragged[1])
        else:
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

    def _resize_edge(
        self,
        drag: _TransformDrag,
        point: tuple[float, float],
        shear_x: float,
        shear_y: float,
    ) -> tuple[Transform, float, float]:
        item = drag.original
        fixed = drag.fixed_world or (item.transform.x, item.transform.y)
        active = transform_local_point(
            item,
            drag.sign_x * item.bounds.width / 2,
            drag.sign_y * item.bounds.height / 2,
        )
        axis_x = active[0] - fixed[0]
        axis_y = active[1] - fixed[1]
        length_sq = axis_x * axis_x + axis_y * axis_y
        if length_sq < 1e-9:
            return item.transform, shear_x, shear_y
        projection = (
            (point[0] - fixed[0]) * axis_x + (point[1] - fixed[1]) * axis_y
        ) / length_sq
        projected = (fixed[0] + axis_x * projection, fixed[1] + axis_y * projection)
        scale_x = item.transform.scale_x
        scale_y = item.transform.scale_y
        if drag.sign_x:
            scale_x = safe_scale(scale_x * projection, scale_x)
        else:
            scale_y = safe_scale(scale_y * projection, scale_y)
        return (
            replace(
                item.transform,
                x=(fixed[0] + projected[0]) / 2,
                y=(fixed[1] + projected[1]) / 2,
                scale_x=scale_x,
                scale_y=scale_y,
            ),
            shear_x,
            shear_y,
        )

    def _draw_selection(self) -> None:
        self.canvas.delete("selection")
        self._screen_handles.clear()
        item = self._active_object()
        if item is None or not item.visible:
            super()._draw_selection()
            return
        offset = 28.0 / max(self._preview_scale, 1e-9)
        handles = object_affine_handles(item, offset=offset)
        corners = tuple(self._screen_point(point) for point in handles.corners)
        edges = tuple(self._screen_point(point) for point in handles.edge_midpoints)
        rotation = self._screen_point(handles.rotation)
        shear_x = self._screen_point(handles.shear_x)
        shear_y = self._screen_point(handles.shear_y)
        center = self._screen_point(handles.center)
        color = COLORS["warning"] if item.locked else COLORS["accent_dark"]
        flattened = [coordinate for point in corners for coordinate in point]
        self.canvas.create_polygon(
            *flattened,
            fill="",
            outline=color,
            width=2,
            dash=(5, 3),
            tags="selection",
        )
        self.canvas.create_line(
            *edges[0],
            *rotation,
            fill=color,
            width=1,
            tags="selection",
        )
        names = ("nw", "ne", "se", "sw")
        for name, point in zip(names, corners, strict=True):
            self._screen_handles[name] = point
            self._draw_square_handle(point, color)
        edge_names = ("n", "e", "s", "w")
        for name, point in zip(edge_names, edges, strict=True):
            self._screen_handles[name] = point
            self._draw_square_handle(point, color, radius=4.5)
        self._screen_handles["rotate"] = rotation
        self.canvas.create_oval(
            rotation[0] - _HANDLE_RADIUS,
            rotation[1] - _HANDLE_RADIUS,
            rotation[0] + _HANDLE_RADIUS,
            rotation[1] + _HANDLE_RADIUS,
            fill=COLORS["white"],
            outline=color,
            width=2,
            tags="selection",
        )
        for name, point in (("shear_x", shear_x), ("shear_y", shear_y)):
            self._screen_handles[name] = point
            self.canvas.create_polygon(
                point[0],
                point[1] - _HANDLE_RADIUS,
                point[0] + _HANDLE_RADIUS,
                point[1],
                point[0],
                point[1] + _HANDLE_RADIUS,
                point[0] - _HANDLE_RADIUS,
                point[1],
                fill="#D9A566",
                outline=color,
                width=1,
                tags="selection",
            )
        self.canvas.create_oval(
            center[0] - 2.5,
            center[1] - 2.5,
            center[0] + 2.5,
            center[1] + 2.5,
            fill=color,
            outline="",
            tags="selection",
        )

    def _draw_square_handle(
        self,
        point: tuple[float, float],
        color: str,
        *,
        radius: float = _HANDLE_RADIUS,
    ) -> None:
        self.canvas.create_rectangle(
            point[0] - radius,
            point[1] - radius,
            point[0] + radius,
            point[1] + radius,
            fill=COLORS["white"],
            outline=color,
            width=1,
            tags="selection",
        )

    def _hit_transform_handle(self, x: float, y: float) -> str | None:
        ordered = (
            "rotate",
            "shear_x",
            "shear_y",
            "nw",
            "ne",
            "se",
            "sw",
            "n",
            "e",
            "s",
            "w",
        )
        for name in ordered:
            point = self._screen_handles.get(name)
            if point is not None and math.hypot(x - point[0], y - point[1]) <= _HANDLE_HIT_RADIUS:
                return name
        return None

    def _screen_point(self, point: tuple[float, float]) -> tuple[float, float]:
        return (
            self._preview_left + point[0] * self._preview_scale,
            self._preview_top + point[1] * self._preview_scale,
        )

    def _cancel_affine_drag(self, _event: tk.Event[tk.Misc]) -> str | None:
        if self._affine_drag is None:
            return None
        self._transform_session.cancel_interactive_object_transform()
        self._affine_drag = None
        self.canvas.configure(cursor="arrow")
        self.refresh_context()
        return "break"

    @property
    def _transform_session(self) -> InteractiveTransformProjectSession:
        if not isinstance(self.session, InteractiveTransformProjectSession):
            raise RuntimeError("Workspace memerlukan InteractiveTransformProjectSession.")
        return self.session

    @staticmethod
    def _cursor_for_mode(mode: str) -> str:
        return {
            "move": "fleur",
            "rotate": "exchange",
            "n": "sb_v_double_arrow",
            "s": "sb_v_double_arrow",
            "e": "sb_h_double_arrow",
            "w": "sb_h_double_arrow",
            "shear_x": "sb_h_double_arrow",
            "shear_y": "sb_v_double_arrow",
        }.get(mode, "sizing")

    @staticmethod
    def _transform_status(mode: str) -> str:
        return {
            "move": "Posisi objek diperbarui langsung di canvas.",
            "rotate": "Rotasi objek diperbarui langsung di canvas.",
            "shear_x": "Shear horizontal objek diperbarui.",
            "shear_y": "Shear vertikal objek diperbarui.",
        }.get(mode, "Ukuran objek diperbarui langsung di canvas.")


def _unrotate_delta(delta_x: float, delta_y: float, degrees: float) -> tuple[float, float]:
    angle = math.radians(degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return (
        cos_a * delta_x + sin_a * delta_y,
        -sin_a * delta_x + cos_a * delta_y,
    )


__all__ = ["WysiwygTransformEditorWorkspaceView"]
