"""Runtime canvas optimizations for responsive object transforms.

The editor's rendering stack is intentionally kept unchanged. This module
adds a thin interaction scheduler around the existing WYSIWYG and multi-object
handlers so pointer bursts are coalesced into one preview update per frame.
It also replaces the thread-per-render viewport path with a single persistent
worker and one latest pending request.

The patch is installed explicitly by :mod:`batikcraft_studio.__main__` before
``ContextToolApplication`` imports the editor classes.
"""

from __future__ import annotations

import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from PIL import Image

from batikcraft_studio.application import ProjectSessionError
from batikcraft_studio.domain import ProjectValidationError
from batikcraft_studio.i18n import tr
from batikcraft_studio.imaging.tile_cache import visible_tile_coords

from .multi_object_editor import MultiObjectEditorWorkspaceView
from .viewport_editor import ViewportEditorWorkspaceView
from .wysiwyg_transform_editor import (
    _SHIFT_MASK,
    WysiwygTransformEditorWorkspaceView,
)

_INTERACTIVE_FRAME_MS = 33
_INSTALLED = False


@dataclass(slots=True)
class _TileRenderRequest:
    project: Any
    assets: dict[str, bytes]
    project_revision: int
    visibility_revision: int
    zoom_scale: float
    generation: int
    preview_left: float
    preview_top: float
    tile_coords: tuple[tuple[int, int], ...]


def install_realtime_canvas_patch() -> None:
    """Install the canvas interaction optimizations once per process."""

    global _INSTALLED
    if _INSTALLED:
        return
    _patch_viewport_renderer()
    _patch_affine_drag()
    _patch_multi_object_drag()
    _INSTALLED = True


def _patch_viewport_renderer() -> None:
    cls = ViewportEditorWorkspaceView
    original_init = cls.__init__

    def optimized_init(self: ViewportEditorWorkspaceView, *args: object, **kwargs: object) -> None:
        self._realtime_render_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="batikcraft-canvas",
        )
        self._realtime_render_running = False
        self._realtime_pending_render: _TileRenderRequest | None = None
        self._realtime_render_closed = False
        original_init(self, *args, **kwargs)
        self.bind("<Destroy>", self._shutdown_realtime_renderer, add="+")

    def optimized_kick_tile_render(
        self: ViewportEditorWorkspaceView,
        project: Any,
        zoom_scale: float,
        generation: int,
        content_width: float,
        content_height: float,
    ) -> None:
        del content_width, content_height
        if self._realtime_render_closed:
            return

        assets = dict(self.session.assets)
        preview_left = self._preview_left
        preview_top = self._preview_top
        vp_left = self.canvas.canvasx(0)
        vp_top = self.canvas.canvasy(0)
        vp_w = max(self.canvas.winfo_width(), 40)
        vp_h = max(self.canvas.winfo_height(), 40)
        proj_left = max(0.0, (vp_left - preview_left) / zoom_scale)
        proj_top = max(0.0, (vp_top - preview_top) / zoom_scale)
        coords = tuple(
            visible_tile_coords(
                proj_left * zoom_scale,
                proj_top * zoom_scale,
                vp_w,
                vp_h,
                project.canvas.width,
                project.canvas.height,
                zoom_scale,
                overscan=1,
            )
        )
        request = _TileRenderRequest(
            project=project,
            assets=assets,
            project_revision=self._compute_project_revision(project, assets),
            visibility_revision=self._compute_visibility_revision(project),
            zoom_scale=zoom_scale,
            generation=generation,
            preview_left=preview_left,
            preview_top=preview_top,
            tile_coords=coords,
        )

        if self._realtime_render_running:
            # Keep only the newest request. Older pending frames have no value
            # once the pointer or zoom state has advanced.
            self._realtime_pending_render = request
            return
        self._start_realtime_render(request)

    def start_realtime_render(
        self: ViewportEditorWorkspaceView,
        request: _TileRenderRequest,
    ) -> None:
        if self._realtime_render_closed:
            return
        self._realtime_render_running = True
        future = self._realtime_render_executor.submit(self._render_tiles_in_worker, request)

        def deliver_result(done: Any) -> None:
            try:
                tiles = done.result()
            except Exception:  # noqa: BLE001
                tiles = []
            try:
                self.after(0, lambda: self._finish_realtime_render(request, tiles))
            except tk.TclError:
                pass

        future.add_done_callback(deliver_result)

    def render_tiles_in_worker(
        self: ViewportEditorWorkspaceView,
        request: _TileRenderRequest,
    ) -> list[tuple[int, int, Image.Image]]:
        tiles: list[tuple[int, int, Image.Image]] = []
        renderer = self._cached_renderer
        for tx, ty in request.tile_coords:
            if request.generation != self._render_generation:
                break
            try:
                image = renderer.get_or_render_tile(
                    request.project,
                    request.assets,
                    project_revision=request.project_revision,
                    visibility_revision=request.visibility_revision,
                    zoom_scale=request.zoom_scale,
                    tile_x=tx,
                    tile_y=ty,
                )
            except Exception:  # noqa: BLE001
                continue
            tiles.append((tx, ty, image))
        return tiles

    def finish_realtime_render(
        self: ViewportEditorWorkspaceView,
        request: _TileRenderRequest,
        tiles: list[tuple[int, int, Image.Image]],
    ) -> None:
        self._realtime_render_running = False
        if (
            not self._realtime_render_closed
            and request.generation == self._render_generation
            and tiles
        ):
            self._apply_tiles(
                tiles,
                request.zoom_scale,
                request.preview_left,
                request.preview_top,
                request.generation,
            )

        pending = self._realtime_pending_render
        self._realtime_pending_render = None
        if pending is not None and not self._realtime_render_closed:
            self._start_realtime_render(pending)

    def shutdown_realtime_renderer(
        self: ViewportEditorWorkspaceView,
        event: tk.Event[tk.Misc],
    ) -> None:
        if event.widget is not self or self._realtime_render_closed:
            return
        self._realtime_render_closed = True
        self._realtime_pending_render = None
        self._realtime_render_executor.shutdown(wait=False, cancel_futures=True)

    cls.__init__ = optimized_init
    cls._kick_tile_render = optimized_kick_tile_render
    cls._start_realtime_render = start_realtime_render
    cls._render_tiles_in_worker = render_tiles_in_worker
    cls._finish_realtime_render = finish_realtime_render
    cls._shutdown_realtime_renderer = shutdown_realtime_renderer


def _patch_affine_drag() -> None:
    cls = WysiwygTransformEditorWorkspaceView
    original_init = cls.__init__
    original_drag = cls._on_canvas_drag
    original_release = cls._on_canvas_release
    original_cancel = cls._cancel_affine_drag

    def optimized_init(
        self: WysiwygTransformEditorWorkspaceView,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._realtime_affine_after_id: str | None = None
        self._realtime_affine_point: tuple[float, float] | None = None
        self._realtime_affine_preserve_ratio = False
        self._realtime_affine_last_screen: tuple[int, int] | None = None
        original_init(self, *args, **kwargs)

    def optimized_drag(
        self: WysiwygTransformEditorWorkspaceView,
        event: tk.Event[tk.Canvas],
    ) -> None:
        drag = self._affine_drag
        if drag is None:
            original_drag(self, event)
            return

        point = self._project_point(event.x, event.y)
        if point is None:
            return

        screen = (event.x, event.y)
        previous = self._realtime_affine_last_screen
        if drag.mode == "move" and previous is not None:
            self.canvas.move("selection", screen[0] - previous[0], screen[1] - previous[1])
        self._realtime_affine_last_screen = screen
        self._realtime_affine_point = point
        self._realtime_affine_preserve_ratio = bool(event.state & _SHIFT_MASK)
        if self._realtime_affine_after_id is None:
            self._realtime_affine_after_id = self.after(
                _INTERACTIVE_FRAME_MS,
                self._apply_realtime_affine_frame,
            )

    def apply_realtime_affine_frame(self: WysiwygTransformEditorWorkspaceView) -> None:
        self._realtime_affine_after_id = None
        drag = self._affine_drag
        point = self._realtime_affine_point
        if drag is None or point is None:
            return
        self._realtime_affine_point = None
        try:
            transform, shear_x, shear_y = self._dragged_geometry(
                drag,
                point,
                preserve_ratio=self._realtime_affine_preserve_ratio,
            )
            self._transform_session.preview_interactive_object_transform(
                drag.object_id,
                transform=transform,
                shear_x=shear_x,
                shear_y=shear_y,
            )
        except (ProjectSessionError, ProjectValidationError, ZeroDivisionError):
            return
        self._draw_selection()
        self._render()

    def flush_realtime_affine_frame(self: WysiwygTransformEditorWorkspaceView) -> None:
        after_id = self._realtime_affine_after_id
        if after_id is not None:
            self.after_cancel(after_id)
            self._realtime_affine_after_id = None
        self._apply_realtime_affine_frame()

    def optimized_release(
        self: WysiwygTransformEditorWorkspaceView,
        event: tk.Event[tk.Canvas],
    ) -> None:
        if self._affine_drag is None:
            original_release(self, event)
            return
        point = self._project_point(event.x, event.y)
        if point is not None:
            self._realtime_affine_point = point
            self._realtime_affine_preserve_ratio = bool(event.state & _SHIFT_MASK)
        self._flush_realtime_affine_frame()
        self._transform_session.commit_interactive_object_transform()
        mode = self._affine_drag.mode
        self._affine_drag = None
        self._realtime_affine_point = None
        self._realtime_affine_last_screen = None
        self.canvas.configure(cursor="arrow")
        self.refresh_context()
        self.set_status(self._transform_status(mode))

    def optimized_cancel(
        self: WysiwygTransformEditorWorkspaceView,
        event: tk.Event[tk.Misc],
    ) -> str | None:
        after_id = self._realtime_affine_after_id
        if after_id is not None:
            self.after_cancel(after_id)
            self._realtime_affine_after_id = None
        self._realtime_affine_point = None
        self._realtime_affine_last_screen = None
        return original_cancel(self, event)

    cls.__init__ = optimized_init
    cls._on_canvas_drag = optimized_drag
    cls._apply_realtime_affine_frame = apply_realtime_affine_frame
    cls._flush_realtime_affine_frame = flush_realtime_affine_frame
    cls._on_canvas_release = optimized_release
    cls._cancel_affine_drag = optimized_cancel


def _patch_multi_object_drag() -> None:
    cls = MultiObjectEditorWorkspaceView
    original_init = cls.__init__
    original_drag = cls._on_canvas_drag
    original_release = cls._on_canvas_release
    original_cancel = cls._cancel_multi_object_interaction

    def optimized_init(
        self: MultiObjectEditorWorkspaceView,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._realtime_multi_after_id: str | None = None
        self._realtime_multi_point: tuple[float, float] | None = None
        self._realtime_multi_last_screen: tuple[int, int] | None = None
        original_init(self, *args, **kwargs)

    def optimized_drag(
        self: MultiObjectEditorWorkspaceView,
        event: tk.Event[tk.Canvas],
    ) -> None:
        if self._multi_move_drag is None:
            original_drag(self, event)
            return
        point = self._project_point(event.x, event.y)
        if point is None:
            return

        screen = (event.x, event.y)
        previous = self._realtime_multi_last_screen
        if previous is not None:
            self.canvas.move("selection", screen[0] - previous[0], screen[1] - previous[1])
        self._realtime_multi_last_screen = screen
        self._realtime_multi_point = point
        if self._realtime_multi_after_id is None:
            self._realtime_multi_after_id = self.after(
                _INTERACTIVE_FRAME_MS,
                self._apply_realtime_multi_frame,
            )

    def apply_realtime_multi_frame(self: MultiObjectEditorWorkspaceView) -> None:
        self._realtime_multi_after_id = None
        drag = self._multi_move_drag
        point = self._realtime_multi_point
        if drag is None or point is None:
            return
        self._realtime_multi_point = None
        start = drag.start_project
        try:
            self._multi_session.preview_interactive_multi_move(
                point[0] - start[0],
                point[1] - start[1],
            )
        except ProjectSessionError:
            return
        self._render()
        self._draw_selection()

    def flush_realtime_multi_frame(self: MultiObjectEditorWorkspaceView) -> None:
        after_id = self._realtime_multi_after_id
        if after_id is not None:
            self.after_cancel(after_id)
            self._realtime_multi_after_id = None
        self._apply_realtime_multi_frame()

    def optimized_release(
        self: MultiObjectEditorWorkspaceView,
        event: tk.Event[tk.Canvas],
    ) -> None:
        if self._multi_move_drag is None:
            original_release(self, event)
            return
        point = self._project_point(event.x, event.y)
        if point is not None:
            self._realtime_multi_point = point
        self._flush_realtime_multi_frame()
        self._multi_session.commit_interactive_multi_move()
        self._multi_move_drag = None
        self._realtime_multi_point = None
        self._realtime_multi_last_screen = None
        self.canvas.configure(cursor="arrow")
        self.refresh_context()
        self.set_status(
            tr("multi.moved", count=len(self._multi_session.selected_object_ids))
        )

    def optimized_cancel(
        self: MultiObjectEditorWorkspaceView,
        event: tk.Event[tk.Misc],
    ) -> str | None:
        after_id = self._realtime_multi_after_id
        if after_id is not None:
            self.after_cancel(after_id)
            self._realtime_multi_after_id = None
        self._realtime_multi_point = None
        self._realtime_multi_last_screen = None
        return original_cancel(self, event)

    cls.__init__ = optimized_init
    cls._on_canvas_drag = optimized_drag
    cls._apply_realtime_multi_frame = apply_realtime_multi_frame
    cls._flush_realtime_multi_frame = flush_realtime_multi_frame
    cls._on_canvas_release = optimized_release
    cls._cancel_multi_object_interaction = optimized_cancel


__all__ = ["install_realtime_canvas_patch"]
