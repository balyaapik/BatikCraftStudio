"""Compatibility between Inkscape-style drag proxies and the safe viewport.

The production editor replaces ``CachedViewportRenderer`` with
``ArtworkViewportRenderer``.  The first retained-overlay implementation only
patched the former, so beginning a multi-object drag raised ``AttributeError``
when it tried to exclude selected objects from the background render.

This module gives the actual screen-tile renderer the same interaction API,
keeps unaffected tiles reusable across a bounded transform, and teaches the
proxy composer to render selected artwork through the safe renderer pipeline.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping
from typing import Any

from PIL import Image

from batikcraft_studio.domain import Project
from batikcraft_studio.imaging.artwork_viewport_renderer import (
    ArtworkViewportRenderer,
    render_project_artwork_region,
)
from batikcraft_studio.imaging.safe_viewport_renderer import SCREEN_TILE_SIZE

from . import inkscape_canvas_patch

_INSTALLED = False


def install_inkscape_renderer_compat() -> None:
    """Install the production-renderer bridge once per process."""

    global _INSTALLED
    if _INSTALLED:
        return
    _patch_artwork_renderer()
    _patch_proxy_composer()
    _INSTALLED = True


def _patch_artwork_renderer() -> None:
    cls = ArtworkViewportRenderer
    if hasattr(cls, "set_interaction_exclusions"):
        return

    original_init = cls.__init__
    original_clear = cls.clear_project
    original_render_tile = cls.render_tile

    def optimized_init(self: ArtworkViewportRenderer, *args: object, **kwargs: object) -> None:
        original_init(self, *args, **kwargs)
        self._inkscape_excluded_object_ids: frozenset[str] = frozenset()
        self._inkscape_interaction_bounds: tuple[float, float, float, float] | None = None
        self._inkscape_known_fingerprint: str | None = None
        self._inkscape_accept_next_fingerprint = False
        self._inkscape_global_epoch = 0
        self._inkscape_tile_epochs: dict[tuple[float, int, int], int] = {}
        self._inkscape_filtered_project_key: tuple[int, int, frozenset[str]] | None = None
        self._inkscape_filtered_project: Project | None = None

    def optimized_clear(self: ArtworkViewportRenderer) -> None:
        original_clear(self)
        with self._lock:
            self._inkscape_interaction_bounds = None
            self._inkscape_known_fingerprint = None
            self._inkscape_accept_next_fingerprint = False
            self._inkscape_global_epoch += 1
            self._inkscape_tile_epochs.clear()
            self._inkscape_filtered_project_key = None
            self._inkscape_filtered_project = None

    def set_interaction_exclusions(
        self: ArtworkViewportRenderer,
        object_ids: Iterable[str],
    ) -> None:
        excluded = frozenset(str(value) for value in object_ids)
        with self._lock:
            self._inkscape_excluded_object_ids = excluded
            self._inkscape_filtered_project_key = None
            self._inkscape_filtered_project = None
            if not excluded:
                self._inkscape_interaction_bounds = None

    def invalidate_project_bounds(
        self: ArtworkViewportRenderer,
        bounds: tuple[float, float, float, float],
        **_metadata: Any,
    ) -> tuple[tuple[int, int], ...]:
        dirty = _normalized_bounds(bounds)
        with self._lock:
            if self._inkscape_excluded_object_ids:
                current = self._inkscape_interaction_bounds
                self._inkscape_interaction_bounds = (
                    dirty if current is None else _union_bounds(current, dirty)
                )
            else:
                # The caller commits the bounded project mutation immediately
                # before the next render.  Accept that next visual fingerprint
                # without discarding cache entries outside the dirty rectangle.
                self._inkscape_accept_next_fingerprint = True

            touched: set[tuple[int, int]] = set()
            keys_to_remove = []
            epoch_keys: set[tuple[float, int, int]] = set()
            for key in self._cache:
                tile_bounds = _screen_key_project_bounds(key)
                if not _bounds_intersect(tile_bounds, dirty):
                    continue
                keys_to_remove.append(key)
                epoch_key = (round(float(key.zoom_scale), 6), key.tile_x, key.tile_y)
                epoch_keys.add(epoch_key)
                touched.add((key.tile_x, key.tile_y))

            for epoch_key in epoch_keys:
                self._inkscape_tile_epochs[epoch_key] = (
                    self._inkscape_tile_epochs.get(epoch_key, 0) + 1
                )
            for key in keys_to_remove:
                image = self._cache.pop(key)
                self._used_bytes -= self._image_bytes(image)
            self._used_bytes = max(0, self._used_bytes)
            return tuple(sorted(touched))

    def optimized_render_tile(
        self: ArtworkViewportRenderer,
        project: Project,
        assets: Mapping[str, bytes],
        *,
        project_fingerprint: str,
        zoom_scale: float,
        tile_x: int,
        tile_y: int,
    ) -> Image.Image:
        scale_key = round(float(zoom_scale), 6)
        epoch_key = (scale_key, int(tile_x), int(tile_y))

        with self._lock:
            known = self._inkscape_known_fingerprint
            if known is None:
                self._inkscape_known_fingerprint = project_fingerprint
            elif project_fingerprint != known:
                if self._inkscape_accept_next_fingerprint:
                    self._inkscape_known_fingerprint = project_fingerprint
                    self._inkscape_accept_next_fingerprint = False
                else:
                    # Unknown edits remain correctness-first: invalidate the
                    # whole scene when no bounded dirty region was announced.
                    self._inkscape_global_epoch += 1
                    self._inkscape_tile_epochs.clear()
                    self._cache.clear()
                    self._used_bytes = 0
                    self._inkscape_known_fingerprint = project_fingerprint

            global_epoch = self._inkscape_global_epoch
            tile_epoch = self._inkscape_tile_epochs.get(epoch_key, 0)
            excluded = self._inkscape_excluded_object_ids
            interaction_bounds = self._inkscape_interaction_bounds

        effective_fingerprint = f"inkscape:{global_epoch}:{tile_epoch}"
        render_project = project
        if excluded and interaction_bounds is not None:
            tile_bounds = _screen_tile_project_bounds(
                zoom_scale,
                tile_x,
                tile_y,
            )
            if _bounds_intersect(tile_bounds, interaction_bounds):
                render_project = _filtered_project(self, project, excluded)
                digest = hashlib.sha1(
                    "\0".join(sorted(excluded)).encode("utf-8"),
                    usedforsecurity=False,
                ).hexdigest()[:12]
                effective_fingerprint += f":exclude:{digest}"

        return original_render_tile(
            self,
            render_project,
            assets,
            project_fingerprint=effective_fingerprint,
            zoom_scale=zoom_scale,
            tile_x=tile_x,
            tile_y=tile_y,
        )

    cls.__init__ = optimized_init
    cls.clear_project = optimized_clear
    cls.set_interaction_exclusions = set_interaction_exclusions
    cls.invalidate_project_bounds = invalidate_project_bounds
    cls.render_tile = optimized_render_tile


def _filtered_project(
    renderer: ArtworkViewportRenderer,
    project: Project,
    excluded: frozenset[str],
) -> Project:
    key = (id(project), int(project.revision), excluded)
    with renderer._lock:
        if renderer._inkscape_filtered_project_key == key:
            cached = renderer._inkscape_filtered_project
            if cached is not None:
                return cached

    layers = []
    for layer in project.layers:
        if not layer.objects:
            layers.append(layer)
            continue
        objects = tuple(item for item in layer.objects if item.object_id not in excluded)
        layers.append(layer if objects == layer.objects else layer.with_updates(objects=objects))

    filtered = Project(
        metadata=project.metadata,
        canvas=project.canvas,
        layers=tuple(layers),
        project_id=project.project_id,
        schema_version=project.schema_version,
        active_layer_id=project.active_layer_id,
        active_object_id=(
            None if project.active_object_id in excluded else project.active_object_id
        ),
        created_at=project.created_at,
        updated_at=project.updated_at,
        revision=project.revision,
        saved_revision=project.saved_revision,
    )
    with renderer._lock:
        renderer._inkscape_filtered_project_key = key
        renderer._inkscape_filtered_project = filtered
    return filtered


def _patch_proxy_composer() -> None:
    original_compose = inkscape_canvas_patch._compose_selection_proxy

    def compatible_compose(
        workspace: Any,
        ordered: list[tuple[Any, Any]],
        bounds: tuple[float, float, float, float],
    ) -> Image.Image | None:
        renderer = workspace._cached_renderer
        if hasattr(renderer, "_get_or_render_object"):
            return original_compose(workspace, ordered, bounds)

        scale = max(float(workspace._preview_scale), 1e-9)
        width = max(1, math.ceil((bounds[2] - bounds[0]) * scale))
        height = max(1, math.ceil((bounds[3] - bounds[1]) * scale))
        if width * height > inkscape_canvas_patch._MAX_PROXY_PIXELS:
            return None

        selected_ids = frozenset(item.object_id for _layer, item in ordered)
        project = workspace.session.require_project()
        layers = []
        for layer in project.layers:
            if not layer.objects:
                layers.append(layer)
                continue
            objects = tuple(item for item in layer.objects if item.object_id in selected_ids)
            layers.append(layer if objects == layer.objects else layer.with_updates(objects=objects))

        proxy_project = Project(
            metadata=project.metadata,
            canvas=project.canvas,
            layers=tuple(layers),
            project_id=project.project_id,
            schema_version=project.schema_version,
            active_layer_id=project.active_layer_id,
            active_object_id=(
                project.active_object_id
                if project.active_object_id in selected_ids
                else None
            ),
            created_at=project.created_at,
            updated_at=project.updated_at,
            revision=project.revision,
            saved_revision=project.saved_revision,
        )
        try:
            return render_project_artwork_region(
                proxy_project,
                dict(workspace.session.assets),
                project_bounds=bounds,
                zoom_scale=scale,
                output_size=(width, height),
            )
        except Exception:  # noqa: BLE001
            return None

    inkscape_canvas_patch._compose_selection_proxy = compatible_compose


def _screen_key_project_bounds(key: Any) -> tuple[float, float, float, float]:
    scale = max(float(key.zoom_scale), 1e-9)
    screen_left = key.tile_x * SCREEN_TILE_SIZE
    screen_top = key.tile_y * SCREEN_TILE_SIZE
    return (
        screen_left / scale,
        screen_top / scale,
        (screen_left + key.output_width) / scale,
        (screen_top + key.output_height) / scale,
    )


def _screen_tile_project_bounds(
    zoom_scale: float,
    tile_x: int,
    tile_y: int,
) -> tuple[float, float, float, float]:
    scale = max(float(zoom_scale), 1e-9)
    screen_left = int(tile_x) * SCREEN_TILE_SIZE
    screen_top = int(tile_y) * SCREEN_TILE_SIZE
    return (
        screen_left / scale,
        screen_top / scale,
        (screen_left + SCREEN_TILE_SIZE) / scale,
        (screen_top + SCREEN_TILE_SIZE) / scale,
    )


def _normalized_bounds(
    bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (float(value) for value in bounds)
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _union_bounds(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        max(first[2], second[2]),
        max(first[3], second[3]),
    )


def _bounds_intersect(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return not (
        first[2] <= second[0]
        or first[0] >= second[2]
        or first[3] <= second[1]
        or first[1] >= second[3]
    )


__all__ = ["install_inkscape_renderer_compat"]
