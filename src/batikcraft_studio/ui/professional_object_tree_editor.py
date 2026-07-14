"""Professional tree presentation and safe object-first canvas selection."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.domain import LayerKind, LayerNodeKind
from batikcraft_studio.imaging import point_hits_layer, point_hits_object

from .object_tree_editor import ObjectTreeEditorWorkspaceView


class ProfessionalObjectTreeEditorWorkspaceView(ObjectTreeEditorWorkspaceView):
    """Keep tree rows clean and avoid hit-testing empty container layers."""

    def _insert_tree_children(self, parent_id: str | None, tree_parent: str) -> None:
        project = self.session.require_project()
        for layer in reversed(project.children_of(parent_id)):
            layer_iid = f"layer:{layer.layer_id}"
            label = layer.name
            if not layer.visible:
                label += "  [tersembunyi]"
            if layer.locked:
                label += "  [terkunci]"
            self.layer_tree.insert(
                tree_parent,
                tk.END,
                iid=layer_iid,
                text=label,
                image=self._tree_icons[
                    "group" if layer.node_kind is LayerNodeKind.GROUP else "layer"
                ],
                open=True,
            )
            if layer.node_kind is LayerNodeKind.GROUP:
                self._insert_tree_children(layer.layer_id, layer_iid)
                continue
            for item in reversed(layer.objects):
                object_label = item.name
                if not item.visible:
                    object_label += "  [tersembunyi]"
                if item.locked:
                    object_label += "  [terkunci]"
                self.layer_tree.insert(
                    layer_iid,
                    tk.END,
                    iid=f"object:{item.object_id}",
                    text=object_label,
                    image=self._tree_icons["object"],
                )

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "select":
            super()._on_canvas_press(event)
            return
        project = self.session.project
        if project is None or self._preview_scale <= 0:
            return
        project_x = (event.x - self._preview_left) / self._preview_scale
        project_y = (event.y - self._preview_top) / self._preview_scale

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
                    if not item.locked and not project.is_layer_effectively_locked(
                        layer.layer_id
                    ):
                        self._drag_object_id = item.object_id
                        self._drag_object_start = (event.x, event.y)
                        self._drag_object_last = (event.x, event.y)
                        self._drag_object_origin = (
                            item.transform.x,
                            item.transform.y,
                        )
                        self.canvas.configure(cursor="fleur")
                    return

        for layer in reversed(project.layers):
            is_legacy_renderable = layer.asset_ref is not None or layer.kind is LayerKind.SHAPE
            if (
                layer.node_kind is LayerNodeKind.LAYER
                and not layer.objects
                and is_legacy_renderable
                and project.is_layer_effectively_visible(layer.layer_id)
                and point_hits_layer(layer, project_x, project_y)
            ):
                self.session.select_layer(layer.layer_id)
                self._refresh_layer_list()
                self._refresh_transform_fields()
                self._draw_selection()
                return

        self.session.select_layer(None)
        self._refresh_layer_list()
        self._refresh_transform_fields()
        self._draw_selection()


__all__ = ["ProfessionalObjectTreeEditorWorkspaceView"]
