"""Final O(1) pointer-motion override for Inkscape-style multi-drag.

The scene/dirty-tile patch creates the drag proxy and owns commit semantics.
This module narrows the actual mouse-motion path to three constant-time tasks:
store the latest delta, move the proxy tag, and raise it above project tiles.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

from batikcraft_studio.application import MultiObjectProjectSession, ProjectSessionError

from .multi_object_editor import MultiObjectEditorWorkspaceView
from .theme import COLORS

_INSTALLED = False


def install_inkscape_pointer_hotpath() -> None:
    """Remove all selected-object iteration from the drag event path."""

    global _INSTALLED
    if _INSTALLED:
        return
    _patch_session_preview()
    _patch_workspace_pointer_path()
    _INSTALLED = True


def _patch_session_preview() -> None:
    cls = MultiObjectProjectSession

    def preview_delta_only(
        self: MultiObjectProjectSession,
        delta_x: float,
        delta_y: float,
    ) -> tuple[Any, ...]:
        if self._multi_move_before is None:
            raise ProjectSessionError("Pemindahan multi-objek belum dimulai.")
        self._inkscape_multi_delta = (float(delta_x), float(delta_y))
        return ()

    cls.preview_interactive_multi_move = preview_delta_only


def _patch_workspace_pointer_path() -> None:
    cls = MultiObjectEditorWorkspaceView
    original_begin_proxy = cls._begin_inkscape_multi_proxy
    original_drag = cls._on_canvas_drag
    original_finish_proxy = cls._finish_inkscape_multi_proxy
    original_draw_selection = cls._draw_selection

    def begin_proxy(
        self: MultiObjectEditorWorkspaceView,
        pointer_screen: tuple[int, int],
    ) -> None:
        original_begin_proxy(self, pointer_screen)
        if not self._inkscape_proxy_active:
            return
        self.canvas.itemconfigure("selection", state="hidden")
        bounds = self._inkscape_proxy_old_bounds
        if self._inkscape_proxy_photo is not None and bounds is not None:
            left, top = self._screen_point((bounds[0], bounds[1]))
            right, bottom = self._screen_point((bounds[2], bounds[3]))
            self.canvas.create_rectangle(
                left,
                top,
                right,
                bottom,
                outline=COLORS["accent_dark"],
                width=2,
                dash=(8, 4),
                tags="drag-proxy",
            )
        self.canvas.tag_raise("drag-proxy")

    def drag_proxy_only(
        self: MultiObjectEditorWorkspaceView,
        event: tk.Event[tk.Canvas],
    ) -> None:
        if not self._inkscape_proxy_active or self._multi_move_drag is None:
            original_drag(self, event)
            return
        point = self._project_point(event.x, event.y)
        if point is None:
            return
        start = self._multi_move_drag.start_project
        delta = (point[0] - start[0], point[1] - start[1])
        try:
            self._multi_session.preview_interactive_multi_move(*delta)
        except ProjectSessionError:
            return
        previous = self._inkscape_proxy_last_screen
        if previous is not None:
            self.canvas.move(
                "drag-proxy",
                event.x - previous[0],
                event.y - previous[1],
            )
        self._inkscape_proxy_last_screen = (event.x, event.y)
        self._inkscape_proxy_delta = delta
        self.canvas.tag_raise("drag-proxy")

    def finish_proxy(self: MultiObjectEditorWorkspaceView) -> None:
        self.canvas.itemconfigure("selection", state="normal")
        original_finish_proxy(self)

    def draw_selection(self: MultiObjectEditorWorkspaceView) -> None:
        if self._inkscape_proxy_active:
            self.canvas.tag_raise("drag-proxy")
            return
        original_draw_selection(self)

    cls._begin_inkscape_multi_proxy = begin_proxy
    cls._on_canvas_drag = drag_proxy_only
    cls._finish_inkscape_multi_proxy = finish_proxy
    cls._draw_selection = draw_selection


__all__ = ["install_inkscape_pointer_hotpath"]
