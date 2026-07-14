"""Canvas selection support for non-asset shape layers."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.domain import Layer
from batikcraft_studio.imaging import (
    ProjectRenderError,
    point_hits_layer,
    transformed_layer_bounds,
)

from .shape_editor import ShapeEditorWorkspaceView
from .theme import COLORS


class SelectableShapeEditorWorkspaceView(ShapeEditorWorkspaceView):
    """Select and transform shape layers through the same canvas workflow."""

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "select":
            super()._on_canvas_press(event)
            return
        project = self.session.project
        if project is None or self._preview_scale <= 0:
            return
        project_x = (event.x - self._preview_left) / self._preview_scale
        project_y = (event.y - self._preview_top) / self._preview_scale
        selected: Layer | None = None
        for layer in reversed(project.layers):
            if layer.visible and point_hits_layer(layer, project_x, project_y):
                selected = layer
                break
        if selected is None:
            self.session.select_layer(None)
            self._refresh_layer_list()
            self._refresh_transform_fields()
            self._draw_selection()
            return

        self.session.select_layer(selected.layer_id)
        self._refresh_layer_list()
        self._refresh_transform_fields()
        self._draw_selection()
        if not selected.locked:
            self._drag_layer_id = selected.layer_id
            self._drag_start = (event.x, event.y)
            self._drag_last = (event.x, event.y)
            self._drag_origin = (selected.transform.x, selected.transform.y)
            self.canvas.configure(cursor="fleur")

    def _draw_selection(self) -> None:
        self.canvas.delete("selection")
        layer = self._active_layer()
        if layer is None or not layer.visible:
            return
        try:
            left, top, right, bottom = transformed_layer_bounds(
                layer,
                preview_scale=self._preview_scale,
            )
        except ProjectRenderError:
            return
        color = COLORS["warning"] if layer.locked else COLORS["accent_dark"]
        coordinates = (
            self._preview_left + left,
            self._preview_top + top,
            self._preview_left + right,
            self._preview_top + bottom,
        )
        self.canvas.create_rectangle(
            *coordinates,
            outline=color,
            width=2,
            dash=(5, 3),
            tags="selection",
        )
        for x, y in (
            (coordinates[0], coordinates[1]),
            (coordinates[2], coordinates[1]),
            (coordinates[0], coordinates[3]),
            (coordinates[2], coordinates[3]),
        ):
            self.canvas.create_rectangle(
                x - 4,
                y - 4,
                x + 4,
                y + 4,
                fill=color,
                outline=COLORS["white"],
                tags="selection",
            )
