"""Safety hotfixes for the contextual editor viewport.

The M4J implementation treated a 512 unit project tile as a 512 pixel screen
tile.  At 800% zoom that produced 4096x4096 Pillow images.  This subclass keeps
tiles bounded to 512 physical output pixels, snapshots project state before
worker rendering, never calls Tk from a worker thread, and releases invisible
``PhotoImage`` instances.
"""

from __future__ import annotations

import copy
import queue
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from PIL import Image, ImageTk

from batikcraft_studio.imaging.safe_viewport_renderer import (
    SCREEN_TILE_SIZE,
    SafeViewportRenderer,
    project_visual_fingerprint,
    visible_screen_tile_coords,
)

from .context_tool_editor import ContextToolEditorWorkspaceView as _BaseContextToolEditor


class ContextToolEditorWorkspaceView(_BaseContextToolEditor):
    """Context editor with bounded, cancellable, main-thread-safe rendering."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._safe_renderer = SafeViewportRenderer()
        self._render_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="batikcraft-viewport",
        )
        self._render_results: queue.SimpleQueue[
            tuple[
                int,
                list[tuple[int, int, Image.Image]],
                float,
                float,
                float,
                frozenset[tuple[int, int]],
            ]
        ] = queue.SimpleQueue()
        self._render_future: Future[None] | None = None
        self._render_shutdown = False
        super().__init__(*args, **kwargs)
        # Replace the legacy renderer before the first scheduled render executes.
        legacy = getattr(self, "_cached_renderer", None)
        if legacy is not None:
            try:
                legacy.clear_project()
            except Exception:  # noqa: BLE001
                pass
        self._cached_renderer = self._safe_renderer
        self.after(16, self._poll_render_results)

    def _set_fixed_zoom(
        self,
        scale: float,
        *,
        anchor_screen: tuple[int, int] | None = None,
    ) -> None:
        # Do not keep wrongly-scaled Tk tiles while waiting for the new generation.
        self._delete_all_screen_tiles()
        super()._set_fixed_zoom(scale, anchor_screen=anchor_screen)

    def _show_quick_preview(
        self,
        old_scale: float,
        new_scale: float,
        anchor_proj: tuple[float, float] | None,
    ) -> None:
        # The previous quick preview stitched visible tiles into another giant image.
        # Keeping the UI responsive is preferable to allocating that duplicate buffer.
        del old_scale, new_scale, anchor_proj

    def _stitch_preview_pil(
        self,
        tiles: list[tuple[int, int, Image.Image]],
        zoom_scale: float,
        preview_left: float,
        preview_top: float,
    ) -> None:
        # Intentionally disabled: individual tiles are already the preview.
        del tiles, zoom_scale, preview_left, preview_top
        self._last_preview_pil = None
        self._preview_photo = None
        self._preview_canvas_id = None

    def _kick_tile_render(
        self,
        project: Any,
        zoom_scale: float,
        generation: int,
        content_width: float,
        content_height: float,
    ) -> None:
        del content_width, content_height
        self._submit_visible_tiles(project, zoom_scale, generation)

    def _schedule_tile_update(self) -> None:
        project = self.session.project
        if project is None or self._preview_scale <= 0 or self._render_shutdown:
            return
        generation = self._increment_render_generation()
        self._submit_visible_tiles(project, self._preview_scale, generation)

    def _submit_visible_tiles(
        self,
        project: Any,
        zoom_scale: float,
        generation: int,
    ) -> None:
        if self._render_shutdown:
            return

        # Cancel queued work. A running worker observes generation changes and exits.
        if self._render_future is not None and not self._render_future.done():
            self._render_future.cancel()

        project_snapshot = copy.deepcopy(project)
        assets_snapshot = {key: bytes(value) for key, value in self.session.assets.items()}
        fingerprint = project_visual_fingerprint(project_snapshot, assets_snapshot)
        preview_left = float(self._preview_left)
        preview_top = float(self._preview_top)

        viewport_left = max(0.0, self.canvas.canvasx(0) - preview_left)
        viewport_top = max(0.0, self.canvas.canvasy(0) - preview_top)
        viewport_width = max(1.0, float(self.canvas.winfo_width()))
        viewport_height = max(1.0, float(self.canvas.winfo_height()))
        tile_coords = visible_screen_tile_coords(
            viewport_left,
            viewport_top,
            viewport_width,
            viewport_height,
            project_snapshot.canvas.width,
            project_snapshot.canvas.height,
            zoom_scale,
            overscan=1,
        )
        active_keys = frozenset(tile_coords)
        renderer = self._safe_renderer

        def worker() -> None:
            rendered: list[tuple[int, int, Image.Image]] = []
            for tile_x, tile_y in tile_coords:
                if self._render_shutdown or generation != self._render_generation:
                    return
                image = renderer.render_tile(
                    project_snapshot,
                    assets_snapshot,
                    project_fingerprint=fingerprint,
                    zoom_scale=zoom_scale,
                    tile_x=tile_x,
                    tile_y=tile_y,
                )
                rendered.append((tile_x, tile_y, image))
            if not self._render_shutdown and generation == self._render_generation:
                self._render_results.put(
                    (
                        generation,
                        rendered,
                        zoom_scale,
                        preview_left,
                        preview_top,
                        active_keys,
                    )
                )

        self._render_future = self._render_executor.submit(worker)

    def _poll_render_results(self) -> None:
        if self._render_shutdown:
            return
        latest: tuple[
            int,
            list[tuple[int, int, Image.Image]],
            float,
            float,
            float,
            frozenset[tuple[int, int]],
        ] | None = None
        while True:
            try:
                candidate = self._render_results.get_nowait()
            except queue.Empty:
                break
            if candidate[0] == self._render_generation:
                latest = candidate
        if latest is not None:
            self._apply_screen_tiles(*latest)
        try:
            self.after(16, self._poll_render_results)
        except Exception:  # noqa: BLE001
            self._render_shutdown = True

    def _apply_screen_tiles(
        self,
        generation: int,
        tiles: list[tuple[int, int, Image.Image]],
        zoom_scale: float,
        preview_left: float,
        preview_top: float,
        active_keys: frozenset[tuple[int, int]],
    ) -> None:
        del zoom_scale
        if generation != self._render_generation or self._render_shutdown:
            return

        # Release Tk image references that are no longer in the visible+overscan set.
        stale = set(self._tile_canvas_ids) - set(active_keys)
        for key in stale:
            canvas_id = self._tile_canvas_ids.pop(key, None)
            if canvas_id is not None:
                self.canvas.delete(canvas_id)
            self._tile_photos.pop(key, None)

        for tile_x, tile_y, image in tiles:
            if image.width > SCREEN_TILE_SIZE or image.height > SCREEN_TILE_SIZE:
                raise RuntimeError("oversized viewport tile reached the Tk main thread")
            key = (tile_x, tile_y)
            photo = ImageTk.PhotoImage(image)
            self._tile_photos[key] = photo
            canvas_x = preview_left + tile_x * SCREEN_TILE_SIZE
            canvas_y = preview_top + tile_y * SCREEN_TILE_SIZE
            canvas_id = self._tile_canvas_ids.get(key)
            if canvas_id is None:
                canvas_id = self.canvas.create_image(
                    canvas_x,
                    canvas_y,
                    image=photo,
                    anchor="nw",
                    tags="project-tile",
                )
                self._tile_canvas_ids[key] = canvas_id
            else:
                self.canvas.itemconfigure(canvas_id, image=photo)
                self.canvas.coords(canvas_id, canvas_x, canvas_y)

        self._draw_grid()
        self._draw_selection()
        self._draw_rulers()

    def _clear_tile_overlays(self) -> None:
        self._delete_all_screen_tiles()
        self._safe_renderer.clear_project()
        self._preview_photo = None
        self._preview_canvas_id = None
        self._last_preview_pil = None

    def _delete_all_screen_tiles(self) -> None:
        canvas = getattr(self, "canvas", None)
        if canvas is not None:
            for canvas_id in tuple(getattr(self, "_tile_canvas_ids", {}).values()):
                canvas.delete(canvas_id)
        if hasattr(self, "_tile_canvas_ids"):
            self._tile_canvas_ids.clear()
        if hasattr(self, "_tile_photos"):
            self._tile_photos.clear()

    def destroy(self) -> None:
        self._render_shutdown = True
        self._render_generation += 1
        if self._render_future is not None:
            self._render_future.cancel()
        self._render_executor.shutdown(wait=False, cancel_futures=True)
        self._safe_renderer.clear_project()
        super().destroy()


__all__ = ["ContextToolEditorWorkspaceView"]
