"""Screen-pixel-bounded viewport rendering.

This module replaces the M4J project-space tile assumption with fixed-size
screen tiles. A tile is never larger than ``SCREEN_TILE_SIZE`` in either
output dimension, including at 800% zoom.
"""

from __future__ import annotations

import hashlib
import math
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from PIL import Image

from batikcraft_studio.domain import Project
from batikcraft_studio.imaging.viewport_renderer import render_project_region

SCREEN_TILE_SIZE = 512
_DEFAULT_CACHE_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ScreenTileKey:
    project_fingerprint: str
    zoom_scale: float
    tile_x: int
    tile_y: int
    output_width: int
    output_height: int


def project_visual_fingerprint(project: Project, assets: Mapping[str, bytes]) -> str:
    """Return a deterministic visual-state fingerprint.

    Selection, cursor, tooltips, and other editor-only state are intentionally
    absent. Object properties, transforms, layer state, and asset bytes are
    included so style and fill edits cannot reuse stale cached artwork.
    """

    digest = hashlib.sha256()
    digest.update(repr(project.canvas).encode("utf-8", errors="replace"))
    for layer in project.layers:
        digest.update(repr(layer).encode("utf-8", errors="replace"))
    for ref in sorted(assets):
        content = assets[ref]
        digest.update(ref.encode("utf-8", errors="replace"))
        digest.update(len(content).to_bytes(8, "big", signed=False))
        digest.update(hashlib.sha1(content, usedforsecurity=False).digest())
    return digest.hexdigest()[:24]


def screen_canvas_size(
    project_width: int,
    project_height: int,
    zoom_scale: float,
) -> tuple[int, int]:
    if zoom_scale <= 0:
        raise ValueError("zoom_scale must be positive")
    return (
        max(1, math.ceil(project_width * zoom_scale)),
        max(1, math.ceil(project_height * zoom_scale)),
    )


def visible_screen_tile_coords(
    viewport_left: float,
    viewport_top: float,
    viewport_width: float,
    viewport_height: float,
    project_canvas_width: int,
    project_canvas_height: int,
    zoom_scale: float,
    *,
    tile_size: int = SCREEN_TILE_SIZE,
    overscan: int = 1,
) -> list[tuple[int, int]]:
    """Return visible screen-tile coordinates, bounded to the zoomed canvas."""

    if zoom_scale <= 0:
        raise ValueError("zoom_scale must be positive")
    if tile_size <= 0:
        raise ValueError("tile_size must be positive")

    canvas_w, canvas_h = screen_canvas_size(
        project_canvas_width,
        project_canvas_height,
        zoom_scale,
    )
    max_tx = max(0, math.ceil(canvas_w / tile_size) - 1)
    max_ty = max(0, math.ceil(canvas_h / tile_size) - 1)

    first_tx = max(0, math.floor(viewport_left / tile_size) - overscan)
    first_ty = max(0, math.floor(viewport_top / tile_size) - overscan)
    viewport_right = max(
        viewport_left,
        viewport_left + max(0.0, viewport_width - 1),
    )
    viewport_bottom = max(
        viewport_top,
        viewport_top + max(0.0, viewport_height - 1),
    )
    last_tx = min(max_tx, math.floor(viewport_right / tile_size) + overscan)
    last_ty = min(max_ty, math.floor(viewport_bottom / tile_size) + overscan)

    if last_tx < first_tx or last_ty < first_ty:
        return []
    return [
        (tx, ty)
        for ty in range(first_ty, last_ty + 1)
        for tx in range(first_tx, last_tx + 1)
    ]


def screen_tile_geometry(
    project_canvas_width: int,
    project_canvas_height: int,
    zoom_scale: float,
    tile_x: int,
    tile_y: int,
    *,
    tile_size: int = SCREEN_TILE_SIZE,
) -> tuple[tuple[float, float, float, float], tuple[int, int]]:
    """Return project bounds and bounded output size for one screen tile."""

    canvas_w, canvas_h = screen_canvas_size(
        project_canvas_width,
        project_canvas_height,
        zoom_scale,
    )
    screen_left = tile_x * tile_size
    screen_top = tile_y * tile_size
    output_w = min(tile_size, canvas_w - screen_left)
    output_h = min(tile_size, canvas_h - screen_top)
    if output_w <= 0 or output_h <= 0:
        raise ValueError("tile coordinate is outside the zoomed project canvas")

    project_left = screen_left / zoom_scale
    project_top = screen_top / zoom_scale
    project_right = min(
        project_canvas_width,
        (screen_left + output_w) / zoom_scale,
    )
    project_bottom = min(
        project_canvas_height,
        (screen_top + output_h) / zoom_scale,
    )
    return (
        (project_left, project_top, project_right, project_bottom),
        (output_w, output_h),
    )


class SafeViewportRenderer:
    """Thread-safe LRU cache for fixed screen-size viewport tiles."""

    def __init__(self, max_bytes: int = _DEFAULT_CACHE_BYTES) -> None:
        self._max_bytes = max(1, int(max_bytes))
        self._used_bytes = 0
        self._cache: OrderedDict[ScreenTileKey, Image.Image] = OrderedDict()
        self._lock = threading.RLock()

    def clear_project(self) -> None:
        with self._lock:
            self._cache.clear()
            self._used_bytes = 0

    def render_tile(
        self,
        project: Project,
        assets: Mapping[str, bytes],
        *,
        project_fingerprint: str,
        zoom_scale: float,
        tile_x: int,
        tile_y: int,
    ) -> Image.Image:
        bounds, output_size = screen_tile_geometry(
            project.canvas.width,
            project.canvas.height,
            zoom_scale,
            tile_x,
            tile_y,
        )
        key = ScreenTileKey(
            project_fingerprint=project_fingerprint,
            zoom_scale=round(float(zoom_scale), 6),
            tile_x=tile_x,
            tile_y=tile_y,
            output_width=output_size[0],
            output_height=output_size[1],
        )
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached

        image = render_project_region(
            project,
            assets,
            project_bounds=bounds,
            zoom_scale=zoom_scale,
            output_size=output_size,
        )
        if image.width > SCREEN_TILE_SIZE or image.height > SCREEN_TILE_SIZE:
            raise RuntimeError("viewport renderer produced an oversized screen tile")

        with self._lock:
            existing = self._cache.pop(key, None)
            if existing is not None:
                self._used_bytes -= self._image_bytes(existing)
            self._cache[key] = image
            self._used_bytes += self._image_bytes(image)
            self._evict_locked()
        return image

    def debug_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tile_count": len(self._cache),
                "tile_bytes": self._used_bytes,
                "tile_limit": self._max_bytes,
                "max_tile_dimension": max(
                    (max(image.size) for image in self._cache.values()),
                    default=0,
                ),
            }

    @staticmethod
    def _image_bytes(image: Image.Image) -> int:
        return image.width * image.height * len(image.getbands())

    def _evict_locked(self) -> None:
        while self._used_bytes > self._max_bytes and self._cache:
            _key, image = self._cache.popitem(last=False)
            self._used_bytes -= self._image_bytes(image)


__all__ = [
    "SCREEN_TILE_SIZE",
    "SafeViewportRenderer",
    "ScreenTileKey",
    "project_visual_fingerprint",
    "screen_canvas_size",
    "screen_tile_geometry",
    "visible_screen_tile_coords",
]
