"""Zoomable canvas viewport, optional grid/rulers, and standard context actions.

Rendering architecture (M4J overhaul)
--------------------------------------
::

    wheel event
        ↓ immediately: update zoom label + scale preview from last cached image
        ↓ schedule debounce (150 ms)
    debounce fires (one render per zoom burst)
        ↓ CachedViewportRenderer.get_or_render_tile()
            ↓ TileCache hit → reuse
            ↓ TileCache miss → ObjectRenderCache → render single object
        ↓ assemble tiles from worker thread (Pillow only)
        ↓ return to Tk main thread → create PhotoImage → place on canvas

Tile placement
--------------
Each 512×512 project-space tile is placed as a separate Tk canvas image so
that only newly-visible tiles need to be re-rendered on scroll.

Generation IDs
--------------
Every final-quality render request bumps ``_render_generation``.  Worker
threads must compare their generation against the current value before
calling back to the main thread.
"""

from __future__ import annotations

import math
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Any

from PIL import Image, ImageTk

from batikcraft_studio.application import ProjectSessionError, ViewportProjectSession
from batikcraft_studio.i18n import tr
from batikcraft_studio.imaging import ProjectRenderError, render_project_preview
from batikcraft_studio.imaging.cached_renderer import CachedViewportRenderer
from batikcraft_studio.imaging.tile_cache import (
    TILE_SIZE,
    tile_project_bounds,
    visible_tile_coords,
    zoom_scale_bucket,
)

from .canvas_structure_editor import (
    CanvasStructureEditorWorkspaceView,
    choose_ruler_step,
    format_ruler_value,
)
from .theme import COLORS

_MIN_ZOOM = 0.10
_MAX_ZOOM = 8.0
_ZOOM_LEVELS = (
    0.10,
    0.125,
    0.16,
    0.20,
    0.25,
    0.33,
    0.50,
    0.67,
    0.75,
    1.0,
    1.25,
    1.50,
    2.0,
    3.0,
    4.0,
    6.0,
    8.0,
)
_VIEW_PADDING = 28
_GRID_BASE = 25.0
_GRID_MINOR = "#B8C0C8"
_GRID_MAJOR = "#8793A0"
_ZOOM_DEBOUNCE_MS = 150  # milliseconds after last zoom event before final render


class ViewportEditorWorkspaceView(CanvasStructureEditorWorkspaceView):
    """Keep project coordinates stable while the viewport zooms and scrolls."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        parent = args[0] if args else kwargs["parent"]
        self.zoom_text_value = tk.StringVar(master=parent, value="Fit")
        self._zoom_mode = "fit"
        self._fixed_zoom_scale = 1.0
        self._grid_visible = False
        self._ruler_visible = True
        self._horizontal_scrollbar: ttk.Scrollbar | None = None
        self._vertical_scrollbar: ttk.Scrollbar | None = None
        self._viewport_ready = False
        # Tile rendering state
        self._cached_renderer = CachedViewportRenderer()
        self._tile_photos: dict[tuple[int, int], tuple[Image.Image, ImageTk.PhotoImage]] = {}
        self._tile_canvas_ids: dict[tuple[int, int], int] = {}
        # Zoom debounce / generation tracking
        self._render_generation = 0
        self._zoom_debounce_id: str | None = None
        # Pointer position for pointer-anchored zoom
        self._last_pointer_screen: tuple[int, int] | None = None
        # Preview (low-quality) image kept for instant feedback
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._preview_canvas_id: int | None = None
        super().__init__(*args, **kwargs)
        self._install_viewport_controls()
        self._viewport_ready = True
        self._schedule_render()

    # ------------------------------------------------------------------
    # Public zoom API
    # ------------------------------------------------------------------

    @property
    def grid_visible(self) -> bool:
        return self._grid_visible

    @property
    def ruler_visible(self) -> bool:
        return self._ruler_visible

    @property
    def zoom_scale(self) -> float:
        return max(_MIN_ZOOM, min(_MAX_ZOOM, float(self._preview_scale)))

    def zoom_in(self) -> None:
        current = self.zoom_scale
        target = next((value for value in _ZOOM_LEVELS if value > current + 1e-9), _MAX_ZOOM)
        self._set_fixed_zoom(target)

    def zoom_out(self) -> None:
        current = self.zoom_scale
        candidates = [value for value in _ZOOM_LEVELS if value < current - 1e-9]
        self._set_fixed_zoom(candidates[-1] if candidates else _MIN_ZOOM)

    def zoom_actual_size(self) -> None:
        self._set_fixed_zoom(1.0)

    def zoom_fit(self) -> None:
        self._zoom_mode = "fit"
        self._schedule_render()

    # ------------------------------------------------------------------
    # Grid / ruler toggles
    # ------------------------------------------------------------------

    def set_grid_visible(self, visible: bool) -> None:
        self._grid_visible = bool(visible)
        if self._grid_visible:
            self._draw_grid()
            self._draw_selection()
        else:
            self.canvas.delete("canvas-grid")
        self.set_status(
            tr("viewport.grid.on") if self._grid_visible else tr("viewport.grid.off")
        )

    def set_ruler_visible(self, visible: bool) -> None:
        self._ruler_visible = bool(visible)
        shell = self.canvas.master
        if self._ruler_visible:
            shell.columnconfigure(0, minsize=46)
            shell.rowconfigure(0, minsize=24)
            self._ruler_corner.grid()
            self.horizontal_ruler.grid()
            self.vertical_ruler.grid()
            self._draw_rulers()
        else:
            self._ruler_corner.grid_remove()
            self.horizontal_ruler.grid_remove()
            self.vertical_ruler.grid_remove()
            shell.columnconfigure(0, minsize=0)
            shell.rowconfigure(0, minsize=0)
        self.set_status(
            tr("viewport.ruler.on") if self._ruler_visible else tr("viewport.ruler.off")
        )

    # ------------------------------------------------------------------
    # Edit commands
    # ------------------------------------------------------------------

    def cut_selected_objects(self) -> None:
        try:
            removed = self._viewport_session.cut_selected_objects()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(tr("viewport.cut", count=len(removed)))

    def copy_active_object(self) -> None:
        try:
            copied = self._viewport_session.copy_selected_objects()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.set_status(tr("viewport.copied", count=len(copied)))

    def paste_object(self) -> None:
        try:
            pasted = self._viewport_session.paste_selected_objects()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(tr("viewport.pasted", count=len(pasted)))

    def delete_selected_objects(self) -> None:
        try:
            removed = self._viewport_session.delete_selected_objects()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(tr("viewport.deleted", count=len(removed)))

    def delete_active(self) -> None:
        if self._viewport_session.selected_object_ids:
            self.delete_selected_objects()
            return
        super().delete_active()

    # ------------------------------------------------------------------
    # Private zoom implementation
    # ------------------------------------------------------------------

    def _set_fixed_zoom(
        self,
        scale: float,
        *,
        anchor_screen: tuple[int, int] | None = None,
    ) -> None:
        """Set a fixed zoom level.

        Parameters
        ----------
        scale
            Target zoom.
        anchor_screen
            Screen coordinate that should remain stationary.  If None,
            the viewport centre is used.
        """
        new_scale = max(_MIN_ZOOM, min(_MAX_ZOOM, float(scale)))
        old_scale = self._preview_scale if self._preview_scale > 0 else new_scale

        # Capture the project point that should stay fixed.
        if anchor_screen is not None:
            anchor_proj = self._project_point(anchor_screen[0], anchor_screen[1])
        else:
            anchor_proj = self._current_project_center()

        self._zoom_mode = "fixed"
        self._fixed_zoom_scale = new_scale
        self._preview_scale = new_scale

        # Update label immediately (non-blocking)
        self._update_zoom_label()

        # Immediately show a fast preview by scaling the last preview image
        self._show_quick_preview(old_scale, new_scale, anchor_proj)

        # Debounce the final high-quality render
        if self._zoom_debounce_id is not None:
            self.after_cancel(self._zoom_debounce_id)
        self._zoom_debounce_id = self.after(
            _ZOOM_DEBOUNCE_MS,
            self._on_zoom_debounce_fire,
        )

    def _on_zoom_debounce_fire(self) -> None:
        """Called ~150 ms after the last zoom event."""
        self._zoom_debounce_id = None
        self._schedule_render()

    def _show_quick_preview(
        self,
        old_scale: float,
        new_scale: float,
        anchor_proj: tuple[float, float] | None,
    ) -> None:
        """Scale the most-recent preview tile image for instant feedback."""
        if self._preview_photo is None:
            return
        if old_scale <= 0:
            return
        try:
            # Use PIL Image kept in self._last_preview_pil if available
            src: Image.Image | None = getattr(self, "_last_preview_pil", None)
            if src is None:
                return
            ratio = new_scale / old_scale
            new_w = max(1, round(src.width * ratio))
            new_h = max(1, round(src.height * ratio))
            quick = src.resize((new_w, new_h), Image.Resampling.BILINEAR)
            self._preview_photo = ImageTk.PhotoImage(quick)
            if self._preview_canvas_id is not None:
                self.canvas.itemconfigure(self._preview_canvas_id, image=self._preview_photo)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Core render
    # ------------------------------------------------------------------

    def _render(self) -> None:
        """High-quality tile-based render — called after debounce fires."""
        self._render_after_id = None
        generation = self._increment_render_generation()
        old_center = self._current_project_center()
        project = self.session.project
        width = max(self.canvas.winfo_width(), 40)
        height = max(self.canvas.winfo_height(), 40)

        if project is None:
            self._clear_tile_overlays()
            self.canvas.delete("all")
            self.canvas.configure(scrollregion=(0, 0, width, height))
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="Create or open a BatikCraft project to begin.",
                fill=COLORS["muted_ink"],
                font=("Segoe UI", 14),
            )
            self.zoom_text_value.set("Fit")
            self._draw_rulers()
            return

        fit_scale = min(
            max(1.0, width - _VIEW_PADDING * 2) / project.canvas.width,
            max(1.0, height - _VIEW_PADDING * 2) / project.canvas.height,
            1.0,
        )
        desired_scale = (
            fit_scale
            if self._zoom_mode == "fit"
            else max(_MIN_ZOOM, min(_MAX_ZOOM, self._fixed_zoom_scale))
        )
        self._preview_scale = desired_scale

        # Layout geometry
        display_width = max(1, round(project.canvas.width * desired_scale))
        display_height = max(1, round(project.canvas.height * desired_scale))
        content_width = max(width, display_width + _VIEW_PADDING * 2)
        content_height = max(height, display_height + _VIEW_PADDING * 2)

        self._preview_left = (
            (content_width - display_width) / 2
            if content_width == width
            else float(_VIEW_PADDING)
        )
        self._preview_top = (
            (content_height - display_height) / 2
            if content_height == height
            else float(_VIEW_PADDING)
        )

        self.canvas.configure(scrollregion=(0, 0, content_width, content_height))
        self._restore_project_center(old_center, content_width, content_height)
        self._update_zoom_label()

        # Draw structural chrome (shadow box, grid, selection, rulers)
        self.canvas.delete("canvas-shadow")
        self.canvas.delete("canvas-chrome")
        self.canvas.create_rectangle(
            self._preview_left + 7,
            self._preview_top + 7,
            self._preview_left + display_width + 7,
            self._preview_top + display_height + 7,
            fill="#C9C0B3",
            outline="",
            tags="canvas-shadow",
        )

        # Trigger async tile render
        self._kick_tile_render(project, desired_scale, generation, content_width, content_height)

    def _increment_render_generation(self) -> int:
        self._render_generation += 1
        return self._render_generation

    def _kick_tile_render(
        self,
        project: Any,
        zoom_scale: float,
        generation: int,
        content_width: float,
        content_height: float,
    ) -> None:
        """Start background tile rendering; post results back to Tk main thread."""
        assets = dict(self.session.assets)
        project_revision = self._compute_project_revision(project, assets)
        visibility_revision = self._compute_visibility_revision(project)
        canvas_w = project.canvas.width
        canvas_h = project.canvas.height
        preview_left = self._preview_left
        preview_top = self._preview_top
        renderer = self._cached_renderer

        # Determine which tiles are (or will be) visible
        vp_left = self.canvas.canvasx(0)
        vp_top = self.canvas.canvasy(0)
        vp_w = max(self.canvas.winfo_width(), 40)
        vp_h = max(self.canvas.winfo_height(), 40)

        # Convert canvas viewport to project space
        proj_left = max(0.0, (vp_left - preview_left) / zoom_scale)
        proj_top = max(0.0, (vp_top - preview_top) / zoom_scale)

        tile_coords = visible_tile_coords(
            proj_left * zoom_scale,
            proj_top * zoom_scale,
            vp_w,
            vp_h,
            canvas_w,
            canvas_h,
            zoom_scale,
            overscan=1,
        )

        def _worker() -> None:
            tiles: list[tuple[int, int, Image.Image]] = []
            for tx, ty in tile_coords:
                if generation != self._render_generation:
                    return  # stale — abort
                try:
                    img = renderer.get_or_render_tile(
                        project,
                        assets,
                        project_revision=project_revision,
                        visibility_revision=visibility_revision,
                        zoom_scale=zoom_scale,
                        tile_x=tx,
                        tile_y=ty,
                    )
                    tiles.append((tx, ty, img))
                except Exception:  # noqa: BLE001
                    pass
            if generation == self._render_generation:
                self.after(0, lambda: self._apply_tiles(
                    tiles, zoom_scale, preview_left, preview_top, generation
                ))

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def _apply_tiles(
        self,
        tiles: list[tuple[int, int, Image.Image]],
        zoom_scale: float,
        preview_left: float,
        preview_top: float,
        generation: int,
    ) -> None:
        """Called on Tk main thread after worker completes."""
        if generation != self._render_generation:
            return  # stale result, ignore

        tile_px = max(1, round(TILE_SIZE * zoom_scale))
        for tx, ty, img in tiles:
            canvas_x = preview_left + tx * tile_px
            canvas_y = preview_top + ty * tile_px
            source = img
            applied = self._tile_photos.get((tx, ty))
            if (
                applied is not None
                and applied[0] is source
                and (tx, ty) in self._tile_canvas_ids
            ):
                # Unchanged cached tile already on screen: skip PhotoImage copy.
                self.canvas.coords(self._tile_canvas_ids[(tx, ty)], canvas_x, canvas_y)
                continue
            # Scale tile to exact screen size if bucket mismatch
            if img.width != tile_px or img.height != tile_px:
                img = img.resize((tile_px, tile_px), Image.Resampling.BILINEAR)
            photo = ImageTk.PhotoImage(img)
            self._tile_photos[(tx, ty)] = (source, photo)  # keep references
            if (tx, ty) in self._tile_canvas_ids:
                self.canvas.itemconfigure(self._tile_canvas_ids[(tx, ty)], image=photo)
                self.canvas.coords(self._tile_canvas_ids[(tx, ty)], canvas_x, canvas_y)
            else:
                cid = self.canvas.create_image(
                    canvas_x,
                    canvas_y,
                    image=photo,
                    anchor="nw",
                    tags="project-tile",
                )
                self._tile_canvas_ids[(tx, ty)] = cid

        # Keep a full-resolution preview image for quick rescale on zoom
        # (stitch visible tiles into one image for _last_preview_pil)
        self._stitch_preview_pil(tiles, zoom_scale, preview_left, preview_top)

        self._draw_grid()
        self._draw_selection()
        self._draw_rulers()

    def _stitch_preview_pil(
        self,
        tiles: list[tuple[int, int, Image.Image]],
        zoom_scale: float,
        preview_left: float,
        preview_top: float,
    ) -> None:
        if not tiles:
            return
        tile_px = max(1, round(TILE_SIZE * zoom_scale))
        min_tx = min(tx for tx, _, _ in tiles)
        min_ty = min(ty for _, ty, _ in tiles)
        max_tx = max(tx for tx, _, _ in tiles)
        max_ty = max(ty for _, ty, _ in tiles)
        cols = max_tx - min_tx + 1
        rows = max_ty - min_ty + 1
        canvas = Image.new("RGBA", (cols * tile_px, rows * tile_px), (0, 0, 0, 0))
        for tx, ty, img in tiles:
            x = (tx - min_tx) * tile_px
            y = (ty - min_ty) * tile_px
            canvas.paste(img, (x, y))
        self._last_preview_pil = canvas

    def _clear_tile_overlays(self) -> None:
        for cid in self._tile_canvas_ids.values():
            self.canvas.delete(cid)
        self._tile_canvas_ids.clear()
        self._tile_photos.clear()
        self._preview_photo = None
        self._preview_canvas_id = None

    # ------------------------------------------------------------------
    # Revision helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_project_revision(project: Any, assets: dict[str, bytes]) -> int:
        """Return a fast integer revision proxy for the project."""
        # Use the project's own revision counter if available
        rev = getattr(project, "_revision", None)
        if isinstance(rev, int):
            return rev
        # Fallback: hash key project attributes
        return hash((
            id(project),
            getattr(project, "canvas", None),
            len(assets),
        )) & 0x7FFF_FFFF

    @staticmethod
    def _compute_visibility_revision(project: Any) -> int:
        """Return a hash of all layer/object visibility states."""
        parts: list[Any] = []
        for layer in project.layers:
            parts.append(layer.layer_id)
            parts.append(layer.visible)
            parts.append(layer.opacity)
            for obj in layer.objects:
                parts.append(obj.object_id)
                parts.append(obj.visible)
        return hash(tuple(parts)) & 0x7FFF_FFFF

    # ------------------------------------------------------------------
    # Optimized grid drawing (visible range only)
    # ------------------------------------------------------------------

    def _draw_grid(self) -> None:
        self.canvas.delete("canvas-grid")
        project = self.session.project
        if not self._grid_visible or project is None or self._preview_scale <= 0:
            return
        scale = self._preview_scale
        spacing = _GRID_BASE
        while spacing * scale < 12:
            spacing *= 2
        while spacing * scale > 80 and spacing > _GRID_BASE / 4:
            spacing /= 2
        major_every = 4

        # Compute visible project coordinate range
        vp_left = self.canvas.canvasx(0)
        vp_top = self.canvas.canvasy(0)
        vp_right = vp_left + self.canvas.winfo_width()
        vp_bottom = vp_top + self.canvas.winfo_height()

        proj_left_vis = max(0.0, (vp_left - self._preview_left) / scale)
        proj_top_vis = max(0.0, (vp_top - self._preview_top) / scale)
        proj_right_vis = min(float(project.canvas.width), (vp_right - self._preview_left) / scale)
        proj_bottom_vis = min(float(project.canvas.height), (vp_bottom - self._preview_top) / scale)

        # Canvas pixel boundaries
        canvas_top = self._preview_top
        canvas_bottom = canvas_top + project.canvas.height * scale
        canvas_left = self._preview_left
        canvas_right = canvas_left + project.canvas.width * scale

        first_col = int(math.floor(proj_left_vis / spacing))
        last_col = int(math.ceil(proj_right_vis / spacing))
        first_row = int(math.floor(proj_top_vis / spacing))
        last_row = int(math.ceil(proj_bottom_vis / spacing))

        for index in range(first_col, last_col + 1):
            x = canvas_left + index * spacing * scale
            self.canvas.create_line(
                x, canvas_top, x, canvas_bottom,
                fill=_GRID_MAJOR if index % major_every == 0 else _GRID_MINOR,
                width=1,
                dash=() if index % major_every == 0 else (2, 3),
                tags="canvas-grid",
            )
        for index in range(first_row, last_row + 1):
            y = canvas_top + index * spacing * scale
            self.canvas.create_line(
                canvas_left, y, canvas_right, y,
                fill=_GRID_MAJOR if index % major_every == 0 else _GRID_MINOR,
                width=1,
                dash=() if index % major_every == 0 else (2, 3),
                tags="canvas-grid",
            )
        self.canvas.tag_raise("canvas-grid")
        self.canvas.tag_raise("selection")

    # ------------------------------------------------------------------
    # Ruler rendering (visible range only — unchanged ticks omitted)
    # ------------------------------------------------------------------

    def _draw_rulers(self) -> None:
        if not self._ruler_visible:
            return
        super()._draw_rulers()

    def _draw_horizontal_ticks(
        self,
        project_width: int,
        scale: float,
        major: float,
        minor: float,
    ) -> None:
        width = self.horizontal_ruler.winfo_width()
        offset = self.canvas.canvasx(0)
        # Visible project range
        p_left = max(0.0, (offset - self._preview_left) / scale)
        p_right = min(float(project_width), (offset + width - self._preview_left) / scale)
        first_index = int(math.floor(p_left / minor))
        last_index = int(math.ceil(p_right / minor)) + 1
        for index in range(first_index, last_index):
            value = index * minor
            x = self._preview_left + value * scale - offset
            if x < 0 or x > width:
                continue
            is_major = index % 5 == 0
            self.horizontal_ruler.create_line(
                x, 10 if is_major else 17, x, 24, fill="#4A4540",
            )
            if is_major:
                self.horizontal_ruler.create_text(
                    x + 3, 2,
                    text=format_ruler_value(value),
                    anchor="nw",
                    fill="#4A4540",
                    font=("TkDefaultFont", 8),
                )

    def _draw_vertical_ticks(
        self,
        project_height: int,
        scale: float,
        major: float,
        minor: float,
    ) -> None:
        height = self.vertical_ruler.winfo_height()
        offset = self.canvas.canvasy(0)
        p_top = max(0.0, (offset - self._preview_top) / scale)
        p_bottom = min(float(project_height), (offset + height - self._preview_top) / scale)
        first_index = int(math.floor(p_top / minor))
        last_index = int(math.ceil(p_bottom / minor)) + 1
        for index in range(first_index, last_index):
            value = index * minor
            y = self._preview_top + value * scale - offset
            if y < 0 or y > height:
                continue
            is_major = index % 5 == 0
            self.vertical_ruler.create_line(
                23 if is_major else 36, y, 46, y, fill="#4A4540",
            )
            if is_major:
                self.vertical_ruler.create_text(
                    2, y + 2,
                    text=format_ruler_value(value),
                    anchor="nw",
                    fill="#4A4540",
                    font=("TkDefaultFont", 8),
                )

    # ------------------------------------------------------------------
    # Coordinate conversion
    # ------------------------------------------------------------------

    def _project_point(self, screen_x: float, screen_y: float) -> tuple[float, float] | None:
        if self._preview_scale <= 0:
            return None
        return (
            (self.canvas.canvasx(screen_x) - self._preview_left) / self._preview_scale,
            (self.canvas.canvasy(screen_y) - self._preview_top) / self._preview_scale,
        )

    def _screen_point(self, point: tuple[float, float]) -> tuple[float, float]:
        return (
            self._preview_left + point[0] * self._preview_scale,
            self._preview_top + point[1] * self._preview_scale,
        )

    def _hit_transform_handle(self, x: float, y: float) -> str | None:
        return super()._hit_transform_handle(self.canvas.canvasx(x), self.canvas.canvasy(y))

    def _begin_marquee(
        self,
        point: tuple[float, float],
        screen: tuple[int, int],
        *,
        extend: bool,
    ) -> None:
        content = (
            round(self.canvas.canvasx(screen[0])),
            round(self.canvas.canvasy(screen[1])),
        )
        super()._begin_marquee(point, content, extend=extend)

    # ------------------------------------------------------------------
    # Canvas event handlers
    # ------------------------------------------------------------------

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool == "hand":
            self.canvas.scan_mark(event.x, event.y)
            self._hand_panning = True
            self.canvas.configure(cursor="fleur")
            return
        if self._ai_selection_active:
            point = self._project_point(event.x, event.y)
            if point is None:
                return
            content = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
            self._ai_selection_start_project = point
            self._ai_selection_start_screen = (round(content[0]), round(content[1]))
            if self._ai_selection_rectangle is not None:
                self.canvas.delete(self._ai_selection_rectangle)
            self._ai_selection_rectangle = self.canvas.create_rectangle(
                content[0], content[1], content[0], content[1],
                outline="#2F6FED", width=2, dash=(6, 3),
            )
            return
        super()._on_canvas_press(event)

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool == "hand":
            if getattr(self, "_hand_panning", False):
                self.canvas.scan_dragto(event.x, event.y, gain=1)
                self._draw_rulers()
            return
        if self._marquee_drag is not None and self._marquee_rectangle is not None:
            start = self._marquee_drag.start_screen
            self.canvas.coords(
                self._marquee_rectangle,
                start[0], start[1],
                self.canvas.canvasx(event.x),
                self.canvas.canvasy(event.y),
            )
            return
        if self._ai_selection_active and self._ai_selection_rectangle is not None:
            start = self._ai_selection_start_screen
            if start is not None:
                self.canvas.coords(
                    self._ai_selection_rectangle,
                    start[0], start[1],
                    self.canvas.canvasx(event.x),
                    self.canvas.canvasy(event.y),
                )
            return
        super()._on_canvas_drag(event)

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool == "hand":
            self._hand_panning = False
            self._draw_rulers()
            self._schedule_tile_update()
            return
        super()._on_canvas_release(event)

    def _draw_preview_dot(self, x: float, y: float) -> None:
        super()._draw_preview_dot(self.canvas.canvasx(x), self.canvas.canvasy(y))

    def _draw_preview_line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        super()._draw_preview_line(
            self.canvas.canvasx(x1), self.canvas.canvasy(y1),
            self.canvas.canvasx(x2), self.canvas.canvasy(y2),
        )

    # ------------------------------------------------------------------
    # Scroll handlers
    # ------------------------------------------------------------------

    def _scroll_x(self, *args: str) -> None:
        self.canvas.xview(*args)
        self._draw_rulers()
        # Render newly-visible tiles without full project re-render
        self._schedule_tile_update()

    def _scroll_y(self, *args: str) -> None:
        self.canvas.yview(*args)
        self._draw_rulers()
        self._schedule_tile_update()

    def _announce_bounded_change(self, bounds: tuple[float, float, float, float] | None) -> None:
        """Umumkan area kotor terbatas ke renderer sebelum re-render.

        Dengan ini hanya tile yang bersinggungan dengan *bounds* yang dirender
        ulang (mis. setelah cap isen/motif atau fill), bukan seluruh scene.
        """
        if bounds is None:
            return
        renderer = getattr(self, "_cached_renderer", None)
        invalidate = getattr(renderer, "invalidate_project_bounds", None)
        if invalidate is None:
            return
        try:
            invalidate(bounds)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _objects_dirty_bounds(objects: object, pad: float = 4.0) -> tuple[float, float, float, float] | None:
        """Union axis-aligned bounds dari kumpulan LayerObject hasil operasi."""
        from batikcraft_studio.imaging.affine_object import object_axis_aligned_bounds

        boxes = []
        try:
            iterator = iter(objects)  # type: ignore[arg-type]
        except TypeError:
            return None
        for item in iterator:
            if hasattr(item, "transform") and hasattr(item, "bounds"):
                try:
                    boxes.append(object_axis_aligned_bounds(item))
                except Exception:  # noqa: BLE001
                    continue
        if not boxes:
            return None
        return (
            min(b[0] for b in boxes) - pad,
            min(b[1] for b in boxes) - pad,
            max(b[2] for b in boxes) + pad,
            max(b[3] for b in boxes) + pad,
        )

    def _schedule_tile_update(self) -> None:
        """Schedule a tile update (does not re-render cached tiles)."""
        project = self.session.project
        if project is None or self._preview_scale <= 0:
            return
        generation = self._render_generation
        assets = dict(self.session.assets)
        zoom = self._preview_scale
        proj_rev = self._compute_project_revision(project, assets)
        vis_rev = self._compute_visibility_revision(project)
        preview_left = self._preview_left
        preview_top = self._preview_top
        renderer = self._cached_renderer

        vp_left = self.canvas.canvasx(0)
        vp_top = self.canvas.canvasy(0)
        vp_w = max(self.canvas.winfo_width(), 40)
        vp_h = max(self.canvas.winfo_height(), 40)
        proj_left = max(0.0, (vp_left - preview_left) / zoom)
        proj_top = max(0.0, (vp_top - preview_top) / zoom)

        tile_coords = visible_tile_coords(
            proj_left * zoom, proj_top * zoom, vp_w, vp_h,
            project.canvas.width, project.canvas.height, zoom, overscan=1,
        )

        def _worker() -> None:
            tiles: list[tuple[int, int, Image.Image]] = []
            for tx, ty in tile_coords:
                if generation != self._render_generation:
                    return
                try:
                    img = renderer.get_or_render_tile(
                        project, assets,
                        project_revision=proj_rev,
                        visibility_revision=vis_rev,
                        zoom_scale=zoom,
                        tile_x=tx, tile_y=ty,
                    )
                    tiles.append((tx, ty, img))
                except Exception:  # noqa: BLE001
                    pass
            if generation == self._render_generation:
                self.after(0, lambda: self._apply_tiles(
                    tiles, zoom, preview_left, preview_top, generation
                ))

        threading.Thread(target=_worker, daemon=True).start()

    def _set_horizontal_scroll(self, first: str, last: str) -> None:
        if self._horizontal_scrollbar is not None:
            self._horizontal_scrollbar.set(first, last)
        if self._viewport_ready:
            self.after_idle(self._draw_rulers)

    def _set_vertical_scroll(self, first: str, last: str) -> None:
        if self._vertical_scrollbar is not None:
            self._vertical_scrollbar.set(first, last)
        if self._viewport_ready:
            self.after_idle(self._draw_rulers)

    # ------------------------------------------------------------------
    # Mouse wheel → zoom (pointer-anchored)
    # ------------------------------------------------------------------

    def _on_control_mousewheel(self, event: tk.Event[tk.Canvas]) -> str:
        self._last_pointer_screen = (event.x, event.y)
        if event.delta > 0:
            self._zoom_in_at(event.x, event.y)
        elif event.delta < 0:
            self._zoom_out_at(event.x, event.y)
        return "break"

    def _zoom_in_at(self, screen_x: int, screen_y: int) -> None:
        current = self.zoom_scale
        target = next((v for v in _ZOOM_LEVELS if v > current + 1e-9), _MAX_ZOOM)
        self._set_fixed_zoom(target, anchor_screen=(screen_x, screen_y))

    def _zoom_out_at(self, screen_x: int, screen_y: int) -> None:
        current = self.zoom_scale
        candidates = [v for v in _ZOOM_LEVELS if v < current - 1e-9]
        target = candidates[-1] if candidates else _MIN_ZOOM
        self._set_fixed_zoom(target, anchor_screen=(screen_x, screen_y))

    def _on_mousewheel(self, event: tk.Event[tk.Canvas]) -> str:
        if event.state & 0x0004:
            return self._on_control_mousewheel(event)
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        self._draw_rulers()
        return "break"

    def _on_shift_mousewheel(self, event: tk.Event[tk.Canvas]) -> str:
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        self._draw_rulers()
        return "break"

    def _on_linux_wheel_up(self, event: tk.Event[tk.Canvas]) -> str:
        if event.state & 0x0004:
            self._zoom_in_at(event.x, event.y)
        else:
            self.canvas.yview_scroll(-1, "units")
            self._draw_rulers()
        return "break"

    def _on_linux_wheel_down(self, event: tk.Event[tk.Canvas]) -> str:
        if event.state & 0x0004:
            self._zoom_out_at(event.x, event.y)
        else:
            self.canvas.yview_scroll(1, "units")
            self._draw_rulers()
        return "break"

    # ------------------------------------------------------------------
    # View center preservation
    # ------------------------------------------------------------------

    def _current_project_center(self) -> tuple[float, float] | None:
        if self.session.project is None or self._preview_scale <= 0:
            return None
        return self._project_point(
            max(1, self.canvas.winfo_width()) / 2,
            max(1, self.canvas.winfo_height()) / 2,
        )

    def _restore_project_center(
        self,
        center: tuple[float, float] | None,
        content_width: float,
        content_height: float,
    ) -> None:
        project = self.session.project
        if project is None:
            return
        target = center or (project.canvas.width / 2, project.canvas.height / 2)
        viewport_width = max(1, self.canvas.winfo_width())
        viewport_height = max(1, self.canvas.winfo_height())
        target_x = self._preview_left + target[0] * self._preview_scale
        target_y = self._preview_top + target[1] * self._preview_scale
        max_x = max(0.0, content_width - viewport_width)
        max_y = max(0.0, content_height - viewport_height)
        left = min(max(0.0, target_x - viewport_width / 2), max_x)
        top = min(max(0.0, target_y - viewport_height / 2), max_y)
        self.canvas.xview_moveto(0.0 if max_x <= 0 else left / content_width)
        self.canvas.yview_moveto(0.0 if max_y <= 0 else top / content_height)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _build_structure_context_menu(self) -> None:
        self._selection_context_menu = tk.Menu(self, tearoff=False)
        for label_key, command, accelerator in (
            ("edit.cut", self.cut_selected_objects, "Ctrl+X"),
            ("edit.copy", self.copy_active_object, "Ctrl+C"),
            ("edit.paste", self.paste_object, "Ctrl+V"),
            ("edit.delete", self.delete_selected_objects, "Delete"),
        ):
            self._selection_context_menu.add_command(
                label=tr(label_key), accelerator=accelerator, command=command,
            )
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label=tr("multi.context.group"), command=self.group_selected_objects,
        )
        self._selection_context_menu.add_command(
            label=tr("multi.context.ungroup"), command=self.ungroup_selected_objects,
        )
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label=tr("structure.context.new_layer"), command=self._create_context_layer,
        )
        self._selection_context_menu.add_command(
            label=tr("structure.context.new_folder"), command=self._create_context_folder,
        )
        self._move_layer_menu = tk.Menu(self._selection_context_menu, tearoff=False)
        self._selection_context_menu.add_cascade(
            label=tr("structure.context.move_to_layer"), menu=self._move_layer_menu,
        )
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label=tr("structure.context.fill_color"), command=self._choose_selected_fill_color,
        )
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label=tr("multi.context.process"), command=self.open_batik_process_studio,
        )

    def _show_selection_context_menu(self, event: tk.Event[tk.Canvas]) -> str | None:
        if self._ai_selection_active or self._active_tool != "select":
            return None
        point = self._project_point(event.x, event.y)
        project = self.session.project
        if point is None or project is None:
            return None
        hit = self._hit_topmost_object(point)
        selected_ids = self._viewport_session.selected_object_ids
        if hit is not None and hit.object_id not in selected_ids:
            self._viewport_session.select_object_for_editing(hit.object_id)
            self._refresh_multi_selection()
        selected = self._viewport_session.selected_objects
        group_ids = {
            str(item.properties["object_group_id"])
            for item in selected
            if item.properties.get("object_group_id")
        }
        same_existing_group = (
            len(group_ids) == 1
            and bool(selected)
            and all(item.properties.get("object_group_id") in group_ids for item in selected)
        )
        closed_shapes = tuple(
            item for item in selected if self._viewport_session.is_closed_shape(item)
        )
        has_selection = bool(selected)
        has_clipboard = (
            self._viewport_session.has_multi_object_clipboard
            or self._viewport_session.has_object_clipboard
        )
        self._populate_move_layer_menu()
        for index in (0, 1, 3):
            self._selection_context_menu.entryconfigure(
                index, state=tk.NORMAL if has_selection else tk.DISABLED,
            )
        self._selection_context_menu.entryconfigure(
            2, state=tk.NORMAL if has_clipboard else tk.DISABLED,
        )
        self._selection_context_menu.entryconfigure(
            5, state=(tk.NORMAL if len(selected) >= 2 and not same_existing_group else tk.DISABLED),
        )
        self._selection_context_menu.entryconfigure(
            6, state=tk.NORMAL if group_ids else tk.DISABLED,
        )
        self._selection_context_menu.entryconfigure(
            10,
            state=(
                tk.NORMAL
                if has_selection and self._viewport_session.object_layers
                else tk.DISABLED
            ),
        )
        self._selection_context_menu.entryconfigure(
            12, state=tk.NORMAL if closed_shapes else tk.DISABLED,
        )
        try:
            self._selection_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._selection_context_menu.grab_release()
        return "break"

    # ------------------------------------------------------------------
    # Zoom label
    # ------------------------------------------------------------------

    def _update_zoom_label(self) -> None:
        percent = round(self._preview_scale * 100)
        self.zoom_text_value.set(
            tr("viewport.zoom.fit_label", percent=percent)
            if self._zoom_mode == "fit"
            else f"{percent}%"
        )

    # ------------------------------------------------------------------
    # Viewport controls installation
    # ------------------------------------------------------------------

    def _install_viewport_controls(self) -> None:
        shell = self.canvas.master
        for widget in shell.grid_slaves(row=2, column=1):
            if isinstance(widget, ttk.Label):
                widget.grid_remove()
        shell.columnconfigure(2, weight=0)
        shell.rowconfigure(2, weight=0)
        shell.rowconfigure(3, weight=0)

        self._vertical_scrollbar = ttk.Scrollbar(
            shell, orient=tk.VERTICAL, command=self._scroll_y,
        )
        self._vertical_scrollbar.grid(row=1, column=2, sticky="ns")
        self._horizontal_scrollbar = ttk.Scrollbar(
            shell, orient=tk.HORIZONTAL, command=self._scroll_x,
        )
        self._horizontal_scrollbar.grid(row=2, column=1, sticky="ew")
        self.canvas.configure(
            xscrollcommand=self._set_horizontal_scroll,
            yscrollcommand=self._set_vertical_scroll,
        )

        status = ttk.Frame(shell, style="Status.TFrame")
        status.grid(row=3, column=1, columnspan=2, sticky="ew")
        status.columnconfigure(0, weight=1)
        ttk.Label(
            status, textvariable=self.canvas_caption,
            style="Status.TLabel", anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        controls = ttk.Frame(status, style="Status.TFrame")
        controls.grid(row=0, column=1, sticky="e", padx=(8, 4))
        ttk.Button(controls, text="−", width=3, command=self.zoom_out).pack(side="left")
        ttk.Label(
            controls, textvariable=self.zoom_text_value,
            style="Status.TLabel", width=10, anchor="center",
        ).pack(side="left", padx=4)
        ttk.Button(controls, text="+", width=3, command=self.zoom_in).pack(side="left")
        ttk.Button(
            controls, text=tr("viewport.fit.short"), width=5, command=self.zoom_fit,
        ).pack(side="left", padx=(4, 0))

        self.canvas.bind("<MouseWheel>", self._on_mousewheel, add="+")
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_mousewheel, add="+")
        self.canvas.bind("<Control-MouseWheel>", self._on_control_mousewheel, add="+")
        self.canvas.bind("<Button-4>", self._on_linux_wheel_up, add="+")
        self.canvas.bind("<Button-5>", self._on_linux_wheel_down, add="+")

    # ------------------------------------------------------------------
    # Session accessor
    # ------------------------------------------------------------------

    @property
    def _viewport_session(self) -> ViewportProjectSession:
        if not isinstance(self.session, ViewportProjectSession):
            raise RuntimeError("Editor viewport memerlukan ViewportProjectSession.")
        return self.session


def choose_grid_step(scale: float, minimum_screen_spacing: float = 12.0) -> float:
    """Return an adaptive project-space grid interval."""
    if scale <= 0 or not math.isfinite(scale):
        return _GRID_BASE
    spacing = _GRID_BASE
    while spacing * scale < minimum_screen_spacing:
        spacing *= 2
    return spacing


__all__ = ["ViewportEditorWorkspaceView", "choose_grid_step"]
