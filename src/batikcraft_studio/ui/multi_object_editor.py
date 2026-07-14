"""Canvas multi-selection, Shift selection, and persistent object groups."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass

from batikcraft_studio.application import MultiObjectProjectSession, ProjectSessionError
from batikcraft_studio.domain import LayerNodeKind, LayerObject
from batikcraft_studio.i18n import tr
from batikcraft_studio.imaging.affine_object import (
    object_affine_handles,
    point_hits_affine_object,
)

from .offline_ai_editor import OfflineAIEditorWorkspaceView
from .theme import COLORS

_SHIFT_MASK = 0x0001


@dataclass(slots=True)
class _MarqueeDrag:
    start_project: tuple[float, float]
    start_screen: tuple[int, int]
    extend: bool


@dataclass(slots=True)
class _MultiMoveDrag:
    start_project: tuple[float, float]


class MultiObjectEditorWorkspaceView(OfflineAIEditorWorkspaceView):
    """Select and move several canvas objects while preserving single-object handles."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._marquee_drag: _MarqueeDrag | None = None
        self._marquee_rectangle: int | None = None
        self._multi_move_drag: _MultiMoveDrag | None = None
        self._selection_syncing = False
        super().__init__(*args, **kwargs)
        self.bind_all("<Escape>", self._cancel_multi_object_interaction, add="+")

    def group_selected_objects(self) -> None:
        try:
            self._multi_session.group_selected_objects()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self._refresh_multi_selection()
        self.set_status(tr("multi.grouped", count=len(self._multi_session.selected_object_ids)))

    def ungroup_selected_objects(self) -> None:
        try:
            groups = self._multi_session.ungroup_selected_objects()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self._refresh_multi_selection()
        self.set_status(tr("multi.ungrouped", count=len(groups)))

    def refresh_project(self) -> None:
        super().refresh_project()
        self._sync_selection_from_active()

    def _on_tree_select(self, event: tk.Event[tk.Misc]) -> None:
        super()._on_tree_select(event)
        if not self._selection_syncing:
            self.after_idle(self._sync_selection_from_active)

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._ai_selection_active or self._active_tool != "select":
            super()._on_canvas_press(event)
            return
        project = self.session.project
        point = self._project_point(event.x, event.y)
        if project is None or point is None:
            return

        selected_ids = self._multi_session.selected_object_ids
        handle = self._hit_transform_handle(event.x, event.y)
        if len(selected_ids) <= 1 and handle is not None:
            super()._on_canvas_press(event)
            return

        hit = self._hit_topmost_object(point)
        extend = bool(event.state & _SHIFT_MASK)
        if hit is None:
            self._begin_marquee(point, (event.x, event.y), extend=extend)
            return

        if extend:
            self._multi_session.select_object_for_editing(hit.object_id, toggle=True)
            self._refresh_multi_selection()
            self.set_status(
                tr("multi.selected", count=len(self._multi_session.selected_object_ids))
            )
            return

        if hit.object_id not in selected_ids:
            self._multi_session.select_object_for_editing(hit.object_id)
            selected_ids = self._multi_session.selected_object_ids
            self._refresh_multi_selection()

        if len(selected_ids) > 1:
            try:
                self._multi_session.begin_interactive_multi_move()
            except ProjectSessionError as exc:
                self.set_status(str(exc))
                return
            self._multi_move_drag = _MultiMoveDrag(start_project=point)
            self.canvas.configure(cursor="fleur")
            return

        super()._on_canvas_press(event)
        active = project.active_object_id
        if active is not None:
            self._multi_session.set_selected_objects([active])

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self._marquee_drag is not None:
            rectangle = self._marquee_rectangle
            if rectangle is not None:
                start = self._marquee_drag.start_screen
                self.canvas.coords(rectangle, start[0], start[1], event.x, event.y)
            return
        if self._multi_move_drag is not None:
            point = self._project_point(event.x, event.y)
            if point is None:
                return
            start = self._multi_move_drag.start_project
            try:
                self._multi_session.preview_interactive_multi_move(
                    point[0] - start[0],
                    point[1] - start[1],
                )
            except ProjectSessionError:
                return
            self._render()
            self._draw_selection()
            return
        super()._on_canvas_drag(event)

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        marquee = self._marquee_drag
        if marquee is not None:
            end = self._project_point(event.x, event.y)
            self._finish_marquee_visuals()
            if end is None:
                self.set_status(tr("multi.marquee_cancelled"))
                return
            selected = self._multi_session.select_objects_in_rectangle(
                (
                    marquee.start_project[0],
                    marquee.start_project[1],
                    end[0],
                    end[1],
                ),
                extend=marquee.extend,
                include_groups=True,
            )
            self._refresh_multi_selection()
            self.set_status(tr("multi.selected", count=len(selected)))
            return

        if self._multi_move_drag is not None:
            self._on_canvas_drag(event)
            self._multi_session.commit_interactive_multi_move()
            self._multi_move_drag = None
            self.canvas.configure(cursor="arrow")
            self.refresh_context()
            self.set_status(
                tr("multi.moved", count=len(self._multi_session.selected_object_ids))
            )
            return

        super()._on_canvas_release(event)
        active = self.session.require_project().active_object_id
        if active is not None:
            self._multi_session.set_selected_objects([active])

    def _draw_selection(self) -> None:
        selected = tuple(item for item in self._multi_session.selected_objects if item.visible)
        if len(selected) <= 1:
            super()._draw_selection()
            return
        self.canvas.delete("selection")
        self._screen_handles.clear()
        for item in selected:
            handles = object_affine_handles(item, offset=0.0)
            corners = tuple(self._screen_point(point) for point in handles.corners)
            self.canvas.create_polygon(
                *(coordinate for point in corners for coordinate in point),
                fill="",
                outline=COLORS["accent_dark"],
                width=2,
                dash=(4, 3),
                tags="selection",
            )
        bounds = self._multi_session.selection_bounds()
        if bounds is None:
            return
        left, top = self._screen_point((bounds[0], bounds[1]))
        right, bottom = self._screen_point((bounds[2], bounds[3]))
        self.canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            outline="#D9A566",
            width=2,
            dash=(8, 4),
            tags="selection",
        )
        self.canvas.create_text(
            left + 6,
            top - 8,
            text=tr("multi.badge", count=len(selected)),
            anchor="sw",
            fill=COLORS["accent_dark"],
            tags="selection",
        )

    def _hit_topmost_object(self, point: tuple[float, float]) -> LayerObject | None:
        project = self.session.project
        if project is None:
            return None
        for layer in reversed(project.layers):
            if layer.node_kind is LayerNodeKind.GROUP:
                continue
            if not project.is_layer_effectively_visible(layer.layer_id):
                continue
            for item in reversed(layer.objects):
                if item.visible and point_hits_affine_object(item, *point):
                    return item
        return None

    def _begin_marquee(
        self,
        point: tuple[float, float],
        screen: tuple[int, int],
        *,
        extend: bool,
    ) -> None:
        self._finish_marquee_visuals()
        self._marquee_drag = _MarqueeDrag(point, screen, extend)
        self._marquee_rectangle = self.canvas.create_rectangle(
            screen[0],
            screen[1],
            screen[0],
            screen[1],
            outline="#2F6FED",
            fill="#DCE8FF",
            stipple="gray25",
            width=1,
            dash=(5, 3),
            tags="marquee-selection",
        )
        self.canvas.configure(cursor="crosshair")

    def _finish_marquee_visuals(self) -> None:
        if self._marquee_rectangle is not None:
            self.canvas.delete(self._marquee_rectangle)
        self._marquee_rectangle = None
        self._marquee_drag = None
        self.canvas.configure(cursor="arrow")

    def _refresh_multi_selection(self) -> None:
        self._selection_syncing = True
        try:
            self._refresh_layer_list()
            self._refresh_transform_fields()
            self._draw_selection()
        finally:
            self._selection_syncing = False
        self.after_idle(lambda: self._sync_palette_from_selection(announce=False))

    def _sync_selection_from_active(self) -> None:
        project = self.session.project
        if project is None:
            self._multi_session.clear_object_selection()
            return
        active = project.active_object_id
        if active is None:
            return
        current = self._multi_session.selected_object_ids
        if active not in current:
            self._multi_session.select_object_for_editing(active)
            self._draw_selection()

    def _cancel_multi_object_interaction(
        self,
        _event: tk.Event[tk.Misc],
    ) -> str | None:
        if self._marquee_drag is not None:
            self._finish_marquee_visuals()
            self.set_status(tr("multi.marquee_cancelled"))
            return "break"
        if self._multi_move_drag is not None:
            self._multi_session.cancel_interactive_multi_move()
            self._multi_move_drag = None
            self.canvas.configure(cursor="arrow")
            self.refresh_context()
            return "break"
        return None

    @property
    def _multi_session(self) -> MultiObjectProjectSession:
        if not isinstance(self.session, MultiObjectProjectSession):
            raise RuntimeError("Editor multi-objek memerlukan MultiObjectProjectSession.")
        return self.session


__all__ = ["MultiObjectEditorWorkspaceView"]
