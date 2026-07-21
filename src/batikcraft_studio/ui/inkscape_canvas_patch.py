"""Inkscape-style multi-object dragging and dirty-region tile invalidation.

This optimization keeps document mutation out of the pointer-motion hot path.
A selection is rendered once into a lightweight drag proxy (or an outline for
very large selections), while the existing project tiles are refreshed without
selected objects.  Mouse motion then moves only canvas overlay items.  On
release, all transforms are committed in one project mutation and only tiles
intersecting the old/new selection bounds are invalidated.
"""

from __future__ import annotations

import math
import threading
import tkinter as tk
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from PIL import Image, ImageEnhance, ImageTk

from batikcraft_studio.application import MultiObjectProjectSession, ProjectSessionError
from batikcraft_studio.application.session import HISTORY_LIMIT
from batikcraft_studio.domain import ObjectKind, ObjectNotFoundError, Project
from batikcraft_studio.i18n import tr
from batikcraft_studio.imaging.cached_renderer import CachedViewportRenderer
from batikcraft_studio.imaging.tile_cache import TILE_SIZE

from .multi_object_editor import MultiObjectEditorWorkspaceView
from .theme import COLORS

_MAX_PROXY_OBJECTS = 160
_MAX_PROXY_PIXELS = 16_000_000
_MAX_PROXY_SIDE = 5_000
_DIRTY_PADDING = 6.0
_INSTALLED = False


def install_inkscape_canvas_patch() -> None:
    """Install retained-overlay dragging and dirty-tile caching once."""

    global _INSTALLED
    if _INSTALLED:
        return
    _patch_project_bulk_updates()
    _patch_cached_renderer()
    _patch_multi_object_session()
    _patch_multi_object_workspace()
    _INSTALLED = True


def _patch_project_bulk_updates() -> None:
    if hasattr(Project, "update_objects_bulk"):
        return

    def update_objects_bulk(
        self: Project,
        changes_by_id: Mapping[str, Mapping[str, Any]],
        *,
        record_change: bool = True,
    ) -> tuple[Any, ...]:
        """Apply updates to many objects with one layer rebuild and revision bump.

        The normal ``update_object`` method is ideal for isolated edits, but a
        collective move used to rebuild layers and increment the project
        revision once per selected object.  This method scans the project once,
        rebuilds each affected layer once, and records one document change.
        """

        requested = {str(object_id): dict(changes) for object_id, changes in changes_by_id.items()}
        if not requested:
            return ()

        replacement_layers = list(self._layers)  # type: ignore[attr-defined]
        found: set[str] = set()
        updated_by_id: dict[str, Any] = {}
        changed_any = False

        for layer_index, layer in enumerate(self._layers):  # type: ignore[attr-defined]
            objects = list(layer.objects)
            layer_changed = False
            for object_index, item in enumerate(objects):
                changes = requested.get(item.object_id)
                if changes is None:
                    continue
                found.add(item.object_id)
                candidate = item.with_updates(**changes)
                updated_by_id[item.object_id] = candidate
                if candidate != item:
                    objects[object_index] = candidate
                    layer_changed = True
                    changed_any = True
            if layer_changed:
                replacement_layers[layer_index] = layer.with_updates(objects=tuple(objects))

        missing = set(requested).difference(found)
        if missing:
            missing_id = sorted(missing)[0]
            raise ObjectNotFoundError(f"Object {missing_id} was not found.")

        if changed_any:
            self._layers = replacement_layers  # type: ignore[attr-defined]
            if record_change:
                self._record_change()  # type: ignore[attr-defined]

        return tuple(updated_by_id[object_id] for object_id in requested)

    Project.update_objects_bulk = update_objects_bulk  # type: ignore[attr-defined]


def _patch_cached_renderer() -> None:
    cls = CachedViewportRenderer
    original_init = cls.__init__
    original_get_or_render_tile = cls.get_or_render_tile
    original_render_object_layer_tile = cls._render_object_layer_tile

    def optimized_init(self: CachedViewportRenderer, *args: object, **kwargs: object) -> None:
        original_init(self, *args, **kwargs)
        self._inkscape_cache_lock = threading.RLock()
        self._inkscape_global_epoch = 0
        self._inkscape_tile_epochs: dict[tuple[int, int], int] = {}
        self._inkscape_known_project_revision: int | None = None
        self._inkscape_known_visibility_revision: int | None = None
        self._inkscape_excluded_object_ids: frozenset[str] = frozenset()

    def optimized_get_or_render_tile(
        self: CachedViewportRenderer,
        project: Project,
        assets: Mapping[str, bytes],
        *,
        project_revision: int,
        visibility_revision: int,
        zoom_scale: float,
        tile_x: int,
        tile_y: int,
    ) -> Image.Image:
        with self._inkscape_cache_lock:
            known_project = self._inkscape_known_project_revision
            known_visibility = self._inkscape_known_visibility_revision
            if known_project is None:
                self._inkscape_known_project_revision = project_revision
                self._inkscape_known_visibility_revision = visibility_revision
            elif project_revision != known_project or visibility_revision != known_visibility:
                # A change not announced through ``invalidate_project_bounds``
                # is treated as a document-wide edit for correctness.
                self._inkscape_global_epoch += 1
                self._inkscape_tile_epochs.clear()
                self._tile_cache.clear()
                self._inkscape_known_project_revision = project_revision
                self._inkscape_known_visibility_revision = visibility_revision

            tile_epoch = self._inkscape_tile_epochs.get((tile_x, tile_y), 0)
            effective_revision = (self._inkscape_global_epoch << 32) | tile_epoch
            return original_get_or_render_tile(
                self,
                project,
                assets,
                project_revision=effective_revision,
                visibility_revision=0,
                zoom_scale=zoom_scale,
                tile_x=tile_x,
                tile_y=tile_y,
            )

    def optimized_render_object_layer_tile(
        self: CachedViewportRenderer,
        layer: Any,
        assets: Mapping[str, bytes],
        proj_bounds: tuple[float, float, float, float],
        zoom_scale: float,
        region_left: float,
        region_top: float,
        out_size: tuple[int, int],
        project_revision: int = 0,
    ) -> Image.Image | None:
        excluded = self._inkscape_excluded_object_ids
        if excluded and layer.objects:
            filtered = tuple(item for item in layer.objects if item.object_id not in excluded)
            if len(filtered) != len(layer.objects):
                layer = layer.with_updates(objects=filtered)
        return original_render_object_layer_tile(
            self,
            layer,
            assets,
            proj_bounds,
            zoom_scale,
            region_left,
            region_top,
            out_size,
            project_revision,
        )

    def set_interaction_exclusions(
        self: CachedViewportRenderer,
        object_ids: tuple[str, ...] | list[str] | set[str] | frozenset[str],
    ) -> None:
        with self._inkscape_cache_lock:
            self._inkscape_excluded_object_ids = frozenset(str(value) for value in object_ids)

    def invalidate_project_bounds(
        self: CachedViewportRenderer,
        bounds: tuple[float, float, float, float],
        *,
        project_revision: int | None = None,
        visibility_revision: int | None = None,
    ) -> tuple[tuple[int, int], ...]:
        left, top, right, bottom = _normalized_bounds(bounds)
        left -= _DIRTY_PADDING
        top -= _DIRTY_PADDING
        right += _DIRTY_PADDING
        bottom += _DIRTY_PADDING
        first_x = math.floor(left / TILE_SIZE)
        first_y = math.floor(top / TILE_SIZE)
        last_x = math.floor(max(left, right - 1e-9) / TILE_SIZE)
        last_y = math.floor(max(top, bottom - 1e-9) / TILE_SIZE)
        coords = tuple(
            (tile_x, tile_y)
            for tile_y in range(first_y, last_y + 1)
            for tile_x in range(first_x, last_x + 1)
            if tile_x >= 0 and tile_y >= 0
        )

        with self._inkscape_cache_lock:
            if project_revision is not None:
                self._inkscape_known_project_revision = int(project_revision)
            if visibility_revision is not None:
                self._inkscape_known_visibility_revision = int(visibility_revision)
            for coord in coords:
                self._inkscape_tile_epochs[coord] = self._inkscape_tile_epochs.get(coord, 0) + 1
            _drop_cached_tile_coords(self._tile_cache, set(coords))
        return coords

    cls.__init__ = optimized_init
    cls.get_or_render_tile = optimized_get_or_render_tile
    cls._render_object_layer_tile = optimized_render_object_layer_tile
    cls.set_interaction_exclusions = set_interaction_exclusions
    cls.invalidate_project_bounds = invalidate_project_bounds


def _drop_cached_tile_coords(tile_cache: Any, coords: set[tuple[int, int]]) -> None:
    if not coords:
        return
    store = tile_cache._store
    keys = [key for key in store if (key.tile_x, key.tile_y) in coords]
    for key in keys:
        image = store.pop(key)
        tile_cache._used_bytes -= image.width * image.height * len(image.getbands())
    tile_cache._used_bytes = max(0, tile_cache._used_bytes)


def _patch_multi_object_session() -> None:
    cls = MultiObjectProjectSession
    original_cancel = cls.cancel_interactive_multi_move

    def optimized_selected_objects(self: MultiObjectProjectSession) -> tuple[Any, ...]:
        project = self.project
        if project is None:
            return ()
        object_map = {
            item.object_id: item
            for layer in project.layers
            for item in layer.objects
        }
        return tuple(
            object_map[object_id]
            for object_id in self.selected_object_ids
            if object_id in object_map
        )

    def optimized_prune_selection(self: MultiObjectProjectSession) -> None:
        project = self.project
        if project is None:
            self._selected_object_ids = []
            return
        valid_ids = {
            item.object_id
            for layer in project.layers
            for item in layer.objects
        }
        valid = [value for value in self._selected_object_ids if value in valid_ids]
        self._selected_object_ids = valid
        if valid:
            project.set_active_object(valid[-1])
        elif project.active_object_id is not None:
            self._selected_object_ids = [project.active_object_id]

    def optimized_begin(
        self: MultiObjectProjectSession,
        object_ids: tuple[str, ...] | list[str] | None = None,
    ) -> tuple[Any, ...]:
        if self.interactive_transform_active:
            self.cancel_interactive_object_transform()
        if self._multi_move_before is not None:
            self.cancel_interactive_multi_move()
        ids = tuple(object_ids) if object_ids is not None else self.selected_object_ids
        if not ids:
            raise ProjectSessionError("Tidak ada objek yang dipilih.")

        project = self.require_project()
        object_map: dict[str, tuple[str, Any]] = {}
        for layer in project.layers:
            for item in layer.objects:
                object_map[item.object_id] = (layer.layer_id, item)

        originals: dict[str, Any] = {}
        ordered_items: list[Any] = []
        layer_lock_cache: dict[str, bool] = {}
        for object_id in ids:
            entry = object_map.get(object_id)
            if entry is None:
                raise ObjectNotFoundError(f"Object {object_id} was not found.")
            layer_id, item = entry
            effectively_locked = layer_lock_cache.setdefault(
                layer_id,
                project.is_layer_effectively_locked(layer_id),
            )
            if item.locked or effectively_locked:
                raise ProjectSessionError(
                    f"Objek {item.name!r} terkunci dan tidak dapat dipindahkan."
                )
            originals[item.object_id] = item.transform
            ordered_items.append(item)

        self._multi_move_before = self._capture_state()
        self._multi_move_originals = originals
        self._selected_object_ids = list(originals)
        project.set_active_object(self._selected_object_ids[-1])
        self._inkscape_multi_delta = (0.0, 0.0)
        return tuple(ordered_items)

    def optimized_preview(
        self: MultiObjectProjectSession,
        delta_x: float,
        delta_y: float,
    ) -> tuple[Any, ...]:
        if self._multi_move_before is None:
            raise ProjectSessionError("Pemindahan multi-objek belum dimulai.")
        dx = float(delta_x)
        dy = float(delta_y)
        self._inkscape_multi_delta = (dx, dy)
        project = self.require_project()
        object_map = {
            item.object_id: item
            for layer in project.layers
            for item in layer.objects
        }
        previews: list[Any] = []
        for object_id, original in self._multi_move_originals.items():
            item = object_map[object_id]
            previews.append(
                replace(
                    item,
                    transform=replace(original, x=original.x + dx, y=original.y + dy),
                )
            )
        return tuple(previews)

    def optimized_commit(self: MultiObjectProjectSession) -> bool:
        before = self._multi_move_before
        if before is None:
            return False
        dx, dy = getattr(self, "_inkscape_multi_delta", (0.0, 0.0))
        changed = abs(dx) > 1e-9 or abs(dy) > 1e-9
        if changed:
            project = self.require_project()
            changes = {
                object_id: {
                    "transform": replace(
                        original,
                        x=original.x + dx,
                        y=original.y + dy,
                    )
                }
                for object_id, original in self._multi_move_originals.items()
            }
            project.update_objects_bulk(changes, record_change=True)  # type: ignore[attr-defined]
            self._undo_stack.append(before)
            if len(self._undo_stack) > HISTORY_LIMIT:
                del self._undo_stack[0]
            self._redo_stack.clear()
        self._multi_move_before = None
        self._multi_move_originals = {}
        self._inkscape_multi_delta = (0.0, 0.0)
        return changed

    def optimized_cancel(self: MultiObjectProjectSession) -> bool:
        changed = original_cancel(self)
        self._inkscape_multi_delta = (0.0, 0.0)
        return changed

    cls.selected_objects = property(optimized_selected_objects)
    cls._prune_selection = optimized_prune_selection
    cls.begin_interactive_multi_move = optimized_begin
    cls.preview_interactive_multi_move = optimized_preview
    cls.commit_interactive_multi_move = optimized_commit
    cls.cancel_interactive_multi_move = optimized_cancel


def _patch_multi_object_workspace() -> None:
    cls = MultiObjectEditorWorkspaceView
    original_init = cls.__init__
    original_press = cls._on_canvas_press
    original_drag = cls._on_canvas_drag
    original_release = cls._on_canvas_release
    original_cancel = cls._cancel_multi_object_interaction
    original_draw_selection = cls._draw_selection

    def optimized_init(
        self: MultiObjectEditorWorkspaceView,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._inkscape_proxy_photo: ImageTk.PhotoImage | None = None
        self._inkscape_proxy_active = False
        self._inkscape_proxy_old_bounds: tuple[float, float, float, float] | None = None
        self._inkscape_proxy_last_screen: tuple[int, int] | None = None
        self._inkscape_proxy_delta = (0.0, 0.0)
        original_init(self, *args, **kwargs)

    def optimized_press(
        self: MultiObjectEditorWorkspaceView,
        event: tk.Event[tk.Canvas],
    ) -> None:
        was_active = self._multi_move_drag is not None
        original_press(self, event)
        if not was_active and self._multi_move_drag is not None:
            self._begin_inkscape_multi_proxy((event.x, event.y))

    def begin_proxy(
        self: MultiObjectEditorWorkspaceView,
        pointer_screen: tuple[int, int],
    ) -> None:
        project = self.session.project
        bounds = self._multi_session.selection_bounds()
        if project is None or bounds is None:
            return
        selected_ids = frozenset(self._multi_session.selected_object_ids)
        ordered: list[tuple[Any, Any]] = []
        for layer in project.layers:
            if not project.is_layer_effectively_visible(layer.layer_id):
                continue
            for item in layer.objects:
                if item.object_id in selected_ids and item.visible:
                    ordered.append((layer, item))
        if not ordered:
            return

        self.canvas.delete("drag-proxy")
        self._inkscape_proxy_photo = None
        self._inkscape_proxy_old_bounds = bounds
        self._inkscape_proxy_last_screen = pointer_screen
        self._inkscape_proxy_delta = (0.0, 0.0)

        # Render tile tanpa objek terpilih DULU: _render() dapat menggeser
        # scroll/offset canvas, jadi proxy harus ditempatkan sesudahnya agar
        # posisinya memakai pemetaan koordinat terbaru.
        self._inkscape_proxy_active = True
        renderer = self._cached_renderer
        renderer.set_interaction_exclusions(selected_ids)  # type: ignore[attr-defined]
        renderer.invalidate_project_bounds(bounds)  # type: ignore[attr-defined]
        self._render()

        if _should_use_outline_proxy(ordered, bounds, self._preview_scale):
            _create_outline_proxy(self, bounds, len(ordered))
        else:
            surface = _compose_selection_proxy(self, ordered, bounds)
            if surface is None:
                _create_outline_proxy(self, bounds, len(ordered))
            else:
                self._inkscape_proxy_photo = ImageTk.PhotoImage(surface)
                left, top = self._screen_point((bounds[0], bounds[1]))
                self.canvas.create_image(
                    left,
                    top,
                    image=self._inkscape_proxy_photo,
                    anchor="nw",
                    tags="drag-proxy",
                )
        self.canvas.tag_raise("drag-proxy")
        self.canvas.tag_raise("selection")

    def optimized_drag(
        self: MultiObjectEditorWorkspaceView,
        event: tk.Event[tk.Canvas],
    ) -> None:
        if not self._inkscape_proxy_active or self._multi_move_drag is None:
            original_drag(self, event)
            return
        point = self._project_point(event.x, event.y)
        delta = self._multi_move_drag.project_delta(event.x, event.y, point)
        if delta is None:
            return
        try:
            self._multi_session.preview_interactive_multi_move(*delta)
        except ProjectSessionError:
            return
        previous = self._inkscape_proxy_last_screen
        if previous is not None:
            dx_screen = event.x - previous[0]
            dy_screen = event.y - previous[1]
            self.canvas.move("drag-proxy", dx_screen, dy_screen)
            self.canvas.move("selection", dx_screen, dy_screen)
        self._inkscape_proxy_last_screen = (event.x, event.y)
        self._inkscape_proxy_delta = delta
        self.canvas.tag_raise("drag-proxy")
        self.canvas.tag_raise("selection")

    def optimized_release(
        self: MultiObjectEditorWorkspaceView,
        event: tk.Event[tk.Canvas],
    ) -> None:
        if not self._inkscape_proxy_active or self._multi_move_drag is None:
            original_release(self, event)
            return

        optimized_drag(self, event)
        old_bounds = self._inkscape_proxy_old_bounds
        delta = self._inkscape_proxy_delta
        renderer = self._cached_renderer
        renderer.set_interaction_exclusions(())  # type: ignore[attr-defined]
        changed = self._multi_session.commit_interactive_multi_move()
        project = self.session.require_project()
        visibility_revision = self._compute_visibility_revision(project)
        if old_bounds is not None:
            renderer.invalidate_project_bounds(
                old_bounds,
                project_revision=project.revision,
                visibility_revision=visibility_revision,
            )  # type: ignore[attr-defined]
            if changed:
                renderer.invalidate_project_bounds(
                    _translate_bounds(old_bounds, *delta),
                    project_revision=project.revision,
                    visibility_revision=visibility_revision,
                )  # type: ignore[attr-defined]

        self._finish_inkscape_multi_proxy()
        self._multi_move_drag = None
        self.canvas.configure(cursor="arrow")
        self.refresh_context()
        self.set_status(tr("multi.moved", count=len(self._multi_session.selected_object_ids)))

    def optimized_cancel(
        self: MultiObjectEditorWorkspaceView,
        event: tk.Event[tk.Misc],
    ) -> str | None:
        if not self._inkscape_proxy_active or self._multi_move_drag is None:
            return original_cancel(self, event)
        bounds = self._inkscape_proxy_old_bounds
        self._cached_renderer.set_interaction_exclusions(())  # type: ignore[attr-defined]
        self._multi_session.cancel_interactive_multi_move()
        project = self.session.require_project()
        if bounds is not None:
            self._cached_renderer.invalidate_project_bounds(
                bounds,
                project_revision=project.revision,
                visibility_revision=self._compute_visibility_revision(project),
            )  # type: ignore[attr-defined]
        self._finish_inkscape_multi_proxy()
        self._multi_move_drag = None
        self.canvas.configure(cursor="arrow")
        self.refresh_context()
        return "break"

    def finish_proxy(self: MultiObjectEditorWorkspaceView) -> None:
        self.canvas.delete("drag-proxy")
        self._inkscape_proxy_photo = None
        self._inkscape_proxy_active = False
        self._inkscape_proxy_old_bounds = None
        self._inkscape_proxy_last_screen = None
        self._inkscape_proxy_delta = (0.0, 0.0)

    def optimized_draw_selection(self: MultiObjectEditorWorkspaceView) -> None:
        if self._inkscape_proxy_active:
            self.canvas.tag_raise("drag-proxy")
            self.canvas.tag_raise("selection")
            return
        original_draw_selection(self)

    cls.__init__ = optimized_init
    cls._on_canvas_press = optimized_press
    cls._begin_inkscape_multi_proxy = begin_proxy
    cls._on_canvas_drag = optimized_drag
    cls._on_canvas_release = optimized_release
    cls._cancel_multi_object_interaction = optimized_cancel
    cls._finish_inkscape_multi_proxy = finish_proxy
    cls._draw_selection = optimized_draw_selection


def _should_use_outline_proxy(
    ordered: list[tuple[Any, Any]],
    bounds: tuple[float, float, float, float],
    scale: float,
) -> bool:
    width = max(1, math.ceil((bounds[2] - bounds[0]) * scale))
    height = max(1, math.ceil((bounds[3] - bounds[1]) * scale))
    return (
        len(ordered) > _MAX_PROXY_OBJECTS
        or width > _MAX_PROXY_SIDE
        or height > _MAX_PROXY_SIDE
        or width * height > _MAX_PROXY_PIXELS
        or any(item.kind is ObjectKind.ERASER_STROKE for _, item in ordered)
    )


def _compose_selection_proxy(
    workspace: MultiObjectEditorWorkspaceView,
    ordered: list[tuple[Any, Any]],
    bounds: tuple[float, float, float, float],
) -> Image.Image | None:
    scale = max(float(workspace._preview_scale), 1e-9)
    width = max(1, math.ceil((bounds[2] - bounds[0]) * scale))
    height = max(1, math.ceil((bounds[3] - bounds[1]) * scale))
    if width * height > _MAX_PROXY_PIXELS:
        return None
    surface = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    assets = dict(workspace.session.assets)
    renderer = workspace._cached_renderer
    project = workspace.session.require_project()

    for layer, item in ordered:
        try:
            prepared = renderer._get_or_render_object(item, assets, zoom_scale=scale).copy()
        except Exception:  # noqa: BLE001
            return None
        layer_opacity = _effective_object_layer_opacity(project, layer)
        if layer_opacity < 1.0:
            alpha = prepared.getchannel("A")
            prepared.putalpha(ImageEnhance.Brightness(alpha).enhance(layer_opacity))
        center_x = (item.transform.x - bounds[0]) * scale
        center_y = (item.transform.y - bounds[1]) * scale
        destination = (
            round(center_x - prepared.width / 2),
            round(center_y - prepared.height / 2),
        )
        surface.alpha_composite(prepared, dest=destination)
    return surface


def _effective_object_layer_opacity(project: Project, layer: Any) -> float:
    opacity = float(layer.opacity)
    current = layer
    visited: set[str] = set()
    while current.parent_id is not None and current.parent_id not in visited:
        visited.add(current.parent_id)
        current = project.get_layer(current.parent_id)
        opacity *= float(current.opacity)
    return max(0.0, min(1.0, opacity))


def _create_outline_proxy(
    workspace: MultiObjectEditorWorkspaceView,
    bounds: tuple[float, float, float, float],
    count: int,
) -> None:
    left, top = workspace._screen_point((bounds[0], bounds[1]))
    right, bottom = workspace._screen_point((bounds[2], bounds[3]))
    workspace.canvas.create_rectangle(
        left,
        top,
        right,
        bottom,
        outline=COLORS["accent_dark"],
        width=2,
        dash=(8, 4),
        tags="drag-proxy",
    )
    workspace.canvas.create_text(
        left + 8,
        top + 8,
        text=f"{count} objek • preview outline",
        anchor="nw",
        fill=COLORS["accent_dark"],
        tags="drag-proxy",
    )


def _normalized_bounds(
    bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (float(value) for value in bounds)
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _translate_bounds(
    bounds: tuple[float, float, float, float],
    delta_x: float,
    delta_y: float,
) -> tuple[float, float, float, float]:
    return (
        bounds[0] + delta_x,
        bounds[1] + delta_y,
        bounds[2] + delta_x,
        bounds[3] + delta_y,
    )


__all__ = ["install_inkscape_canvas_patch"]
