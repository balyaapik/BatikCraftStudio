"""Canvas-native move, rotate, resize, and shear interaction."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from batikcraft_studio.application import (
    InteractiveTransformProjectSession,
    ObjectLockedError,
    ProjectSessionError,
)
from batikcraft_studio.domain import LayerNodeKind, ProjectValidationError
from batikcraft_studio.i18n import tr
from batikcraft_studio.imaging import point_hits_object

from .compact_asset_editor import CompactAssetEditorWorkspaceView
from .theme import COLORS
from .transform_gizmo import (
    TransformPreview,
    build_gizmo_geometry,
    hit_test_gizmo,
    move_preview,
    preview_from_item,
    rotation_preview,
    scale_preview,
    shear_preview,
)
from .wysiwyg_tool_windows import WysiwygToolWindows

_SHIFT_MASK = 0x0001


class WysiwygTransformEditorWorkspaceView(CompactAssetEditorWorkspaceView):
    """Add a live affine transform gizmo to the asset-first workspace."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        parent = args[0] if args else kwargs["parent"]
        self.shear_x_value = tk.StringVar(master=parent, value="0")
        self.shear_y_value = tk.StringVar(master=parent, value="0")
        self._gizmo_mode: str | None = None
        self._gizmo_object_id: str | None = None
        self._gizmo_start_pointer: tuple[float, float] | None = None
        self._gizmo_start_preview: TransformPreview | None = None
        super().__init__(*args, **kwargs)
        self.tool_windows.close_all()
        self.tool_windows = WysiwygToolWindows(self)
        self.canvas.bind("<Motion>", self._on_gizmo_motion, add="+")
        self.bind_all("<Escape>", self._cancel_gizmo_shortcut, add="+")

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "select":
            super()._on_canvas_press(event)
            return
        project = self.session.project
        if project is None or self._preview_scale <= 0:
            return

        active = self._active_object()
        if active is not None:
            geometry = build_gizmo_geometry(
                active,
                preview_left=self._preview_left,
                preview_top=self._preview_top,
                preview_scale=self._preview_scale,
            )
            handle = hit_test_gizmo(geometry, event.x, event.y)
            if handle is not None and self._object_is_editable(active.object_id):
                self._begin_gizmo_drag(active.object_id, handle, event)
                return

        project_x, project_y = self._screen_to_project(event.x, event.y)
        for layer in reversed(project.layers):
            if layer.node_kind is LayerNodeKind.GROUP:
                continue
            if not project.is_layer_effectively_visible(layer.layer_id):
                continue
            for item in reversed(layer.objects):
                if item.visible and point_hits_object(item, project_x, project_y):
                    self._object_session.select_object(item.object_id)
                    self._refresh_layer_list()
                    self._refresh_transform_fields()
                    self._draw_selection()
                    if self._object_is_editable(item.object_id):
                        self._begin_gizmo_drag(item.object_id, "move", event)
                    return
        super()._on_canvas_press(event)

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self._gizmo_mode is None:
            super()._on_canvas_drag(event)
            return
        self._preview_gizmo_drag(event)

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        if self._gizmo_mode is None:
            super()._on_canvas_release(event)
            return
        self._preview_gizmo_drag(event)
        item = self._active_object()
        if item is not None and item.object_id == self._gizmo_object_id:
            shear_x = float(item.properties.get("shear_x", 0.0))
            shear_y = float(item.properties.get("shear_y", 0.0))
            try:
                self._interactive_session.commit_interactive_object_transform(
                    item.object_id,
                    transform=item.transform,
                    shear_x=shear_x,
                    shear_y=shear_y,
                )
            except (ProjectSessionError, ProjectValidationError) as exc:
                self._interactive_session.cancel_interactive_object_transform()
                self.set_status(str(exc))
        self._clear_gizmo_drag()
        self.refresh_context()

    def _begin_gizmo_drag(
        self,
        object_id: str,
        mode: str,
        event: tk.Event[tk.Canvas],
    ) -> None:
        try:
            item = self._interactive_session.begin_interactive_object_transform(object_id)
        except (ObjectLockedError, ProjectSessionError) as exc:
            self.set_status(str(exc))
            return
        self._gizmo_mode = mode
        self._gizmo_object_id = object_id
        self._gizmo_start_pointer = self._screen_to_project(event.x, event.y)
        self._gizmo_start_preview = preview_from_item(item)
        self.canvas.configure(cursor=self._cursor_for_mode(mode))

    def _preview_gizmo_drag(self, event: tk.Event[tk.Canvas]) -> None:
        item = self._active_object()
        start = self._gizmo_start_preview
        start_pointer = self._gizmo_start_pointer
        mode = self._gizmo_mode
        if (
            item is None
            or start is None
            or start_pointer is None
            or mode is None
            or item.object_id != self._gizmo_object_id
        ):
            return
        pointer = self._screen_to_project(event.x, event.y)
        if mode == "move":
            preview = move_preview(
                start,
                delta_x=pointer[0] - start_pointer[0],
                delta_y=pointer[1] - start_pointer[1],
            )
        elif mode == "rotate":
            preview = rotation_preview(
                start,
                center=(start.transform.x, start.transform.y),
                start_pointer=start_pointer,
                pointer=pointer,
                snap=bool(event.state & _SHIFT_MASK),
            )
        elif mode.startswith("scale-"):
            preview = scale_preview(
                start,
                handle=mode,
                pointer=pointer,
                width=item.bounds.width,
                height=item.bounds.height,
            )
        else:
            preview = shear_preview(
                start,
                handle=mode,
                start_pointer=start_pointer,
                pointer=pointer,
                width=item.bounds.width,
                height=item.bounds.height,
            )
        try:
            self._interactive_session.preview_interactive_object_transform(
                item.object_id,
                transform=preview.transform,
                shear_x=preview.shear_x,
                shear_y=preview.shear_y,
            )
        except (ProjectSessionError, ProjectValidationError):
            return
        self._refresh_transform_fields()
        self._schedule_render()
        self._draw_selection()

    def _draw_selection(self) -> None:
        item = self._active_object()
        if item is None or self._preview_scale <= 0:
            super()._draw_selection()
            return
        self.canvas.delete("selection")
        geometry = build_gizmo_geometry(
            item,
            preview_left=self._preview_left,
            preview_top=self._preview_top,
            preview_scale=self._preview_scale,
        )
        color = COLORS["warning"] if item.locked else COLORS["accent_dark"]
        polygon = [coordinate for point in (*geometry.corners, geometry.corners[0]) for coordinate in point]
        self.canvas.create_line(
            *polygon,
            fill=color,
            width=2,
            dash=(5, 3),
            tags="selection",
        )
        if item.locked:
            return
        self.canvas.create_line(
            *geometry.rotation_anchor,
            *geometry.rotation_handle,
            fill=color,
            width=1,
            tags="selection",
        )
        self._draw_circle_handle(geometry.rotation_handle, color, radius=6)
        for point in geometry.scale_handles.values():
            self._draw_square_handle(point, color)
        for point in geometry.shear_handles.values():
            self._draw_diamond_handle(point, COLORS["warning"])
        center_x, center_y = geometry.center
        self.canvas.create_line(
            center_x - 5,
            center_y,
            center_x + 5,
            center_y,
            fill=color,
            tags="selection",
        )
        self.canvas.create_line(
            center_x,
            center_y - 5,
            center_x,
            center_y + 5,
            fill=color,
            tags="selection",
        )

    def _draw_square_handle(self, point: tuple[float, float], color: str) -> None:
        x, y = point
        self.canvas.create_rectangle(
            x - 4,
            y - 4,
            x + 4,
            y + 4,
            fill=color,
            outline=COLORS["white"],
            tags="selection",
        )

    def _draw_diamond_handle(self, point: tuple[float, float], color: str) -> None:
        x, y = point
        self.canvas.create_polygon(
            x,
            y - 6,
            x + 6,
            y,
            x,
            y + 6,
            x - 6,
            y,
            fill=color,
            outline=COLORS["white"],
            tags="selection",
        )

    def _draw_circle_handle(
        self,
        point: tuple[float, float],
        color: str,
        *,
        radius: float,
    ) -> None:
        x, y = point
        self.canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill=COLORS["white"],
            outline=color,
            width=2,
            tags="selection",
        )

    def _on_gizmo_motion(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "select" or self._gizmo_mode is not None:
            return
        item = self._active_object()
        if item is None or item.locked:
            return
        geometry = build_gizmo_geometry(
            item,
            preview_left=self._preview_left,
            preview_top=self._preview_top,
            preview_scale=self._preview_scale,
        )
        handle = hit_test_gizmo(geometry, event.x, event.y)
        self.canvas.configure(cursor=self._cursor_for_mode(handle) if handle else "arrow")

    def _refresh_transform_fields(self) -> None:
        super()._refresh_transform_fields()
        item = self._active_object()
        if item is None:
            self.shear_x_value.set("0")
            self.shear_y_value.set("0")
            return
        self.shear_x_value.set(self._format_number(item.properties.get("shear_x", 0.0)))
        self.shear_y_value.set(self._format_number(item.properties.get("shear_y", 0.0)))

    def apply_transform(self) -> None:
        item = self._active_object()
        if item is None:
            super().apply_transform()
            return
        try:
            self._interactive_session.update_object_transform(
                item.object_id,
                x=float(self.x_value.get()),
                y=float(self.y_value.get()),
                rotation_degrees=float(self.rotation_value.get()),
                scale_x=float(self.scale_x_value.get()),
                scale_y=float(self.scale_y_value.get()),
                shear_x=float(self.shear_x_value.get()),
                shear_y=float(self.shear_y_value.get()),
            )
            self._interactive_session.set_object_opacity(
                item.object_id,
                float(self.opacity_value.get()),
            )
        except (ValueError, ProjectSessionError, ProjectValidationError) as exc:
            messagebox.showerror(
                tr("gizmo.invalid_title"),
                str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh_context()

    def _object_is_editable(self, object_id: str) -> bool:
        project = self.session.require_project()
        item = project.get_object(object_id)
        return not item.locked and not project.is_layer_effectively_locked(
            project.object_layer_id(object_id)
        )

    def _screen_to_project(self, x: float, y: float) -> tuple[float, float]:
        return (
            (x - self._preview_left) / self._preview_scale,
            (y - self._preview_top) / self._preview_scale,
        )

    def _cancel_gizmo_shortcut(self, _event: tk.Event[tk.Misc]) -> str | None:
        if self._gizmo_mode is None:
            return None
        self._interactive_session.cancel_interactive_object_transform()
        self._clear_gizmo_drag()
        self.refresh_context()
        self.set_status(tr("gizmo.cancelled"))
        return "break"

    def _clear_gizmo_drag(self) -> None:
        self._gizmo_mode = None
        self._gizmo_object_id = None
        self._gizmo_start_pointer = None
        self._gizmo_start_preview = None
        self.canvas.configure(cursor="arrow")

    @staticmethod
    def _format_number(value: object) -> str:
        return f"{float(value):.4f}".rstrip("0").rstrip(".")

    @staticmethod
    def _cursor_for_mode(mode: str | None) -> str:
        if mode == "rotate":
            return "crosshair"
        if mode and mode.startswith("shear-"):
            return "fleur"
        if mode and mode.startswith("scale-"):
            if mode in {"scale-e", "scale-w"}:
                return "sb_h_double_arrow"
            if mode in {"scale-n", "scale-s"}:
                return "sb_v_double_arrow"
            return "sizing"
        return "fleur" if mode == "move" else "arrow"

    @property
    def _interactive_session(self) -> InteractiveTransformProjectSession:
        if not isinstance(self.session, InteractiveTransformProjectSession):
            raise RuntimeError("Editor memerlukan session transform interaktif.")
        return self.session


__all__ = ["WysiwygTransformEditorWorkspaceView"]
