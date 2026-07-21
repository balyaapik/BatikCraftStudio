"""Tile-based LRU caches for artwork tiles and object renders.

TileCache
---------
Divides the project canvas into 512×512 tiles and caches rendered Pillow
images.  Only tiles that intersect the viewport are rendered.  Cache entries
are keyed by ``TileCacheKey`` so that irrelevant state (selection, cursor
position) never causes a cache miss.

ObjectRenderCache
-----------------
Caches fully-prepared object images before compositing.  Keyed by
``ObjectRenderCacheKey``.  Uses LRU eviction bounded by a configurable
byte limit.

Both caches expose optional debug statistics (disabled by default).
"""

from __future__ import annotations

import hashlib
import math
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PIL import Image

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TILE_SIZE = 512
_SCALE_BUCKETS = (0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
_DEFAULT_TILE_LIMIT = 128 * 1024 * 1024   # 128 MiB
_DEFAULT_OBJECT_LIMIT = 64 * 1024 * 1024  # 64 MiB


# ---------------------------------------------------------------------------
# Scale bucketing
# ---------------------------------------------------------------------------


def zoom_scale_bucket(zoom: float) -> float:
    """Round *zoom* to the nearest predefined scale bucket."""
    if zoom <= 0:
        return _SCALE_BUCKETS[0]
    best = _SCALE_BUCKETS[0]
    best_dist = abs(math.log(zoom / best))
    for bucket in _SCALE_BUCKETS[1:]:
        dist = abs(math.log(zoom / bucket))
        if dist < best_dist:
            best_dist = dist
            best = bucket
    return best


# ---------------------------------------------------------------------------
# Cache keys
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TileCacheKey:
    """Stable identity for a rendered tile.

    Fields that belong to selection/cursor/tooltip state are intentionally
    excluded so that those events never invalidate artwork tiles.
    """

    project_revision: int
    zoom_bucket: float
    tile_x: int
    tile_y: int
    canvas_background: str
    visibility_revision: int  # bumped when layer/object visibility changes


@dataclass(frozen=True, slots=True)
class ObjectRenderCacheKey:
    """Stable identity for a prepared object image."""

    object_id: str
    asset_ref: str | None
    asset_digest: str  # truncated SHA-1 of asset bytes, "" for shapes
    bounds_w: float
    bounds_h: float
    scale_x: float
    scale_y: float
    rotation_degrees: float
    shear_x: float
    shear_y: float
    fill_mode: str
    gradient_hash: str  # SHA-1 of serialised gradient dict, "" if none
    opacity: float
    render_scale_bucket: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _image_bytes(img: Image.Image) -> int:
    """Approximate memory footprint of a Pillow image."""
    return img.width * img.height * len(img.getbands())


_ASSET_DIGEST_CACHE: dict[int, tuple[bytes, str]] = {}
_ASSET_DIGEST_CACHE_MAX = 512


def _asset_digest(content: bytes | None) -> str:
    """Return a truncated SHA-1 of *content*, memoized by object identity.

    Asset bytes are immutable, so hashing the same object repeatedly (once per
    object per tile per frame) is wasted work.  The cache holds a strong
    reference to each hashed object, which guarantees an ``id()`` can never be
    reused while its entry is alive.
    """
    if content is None:
        return ""
    key = id(content)
    hit = _ASSET_DIGEST_CACHE.get(key)
    if hit is not None and hit[0] is content:
        return hit[1]
    digest = hashlib.sha1(content, usedforsecurity=False).hexdigest()[:16]
    if len(_ASSET_DIGEST_CACHE) >= _ASSET_DIGEST_CACHE_MAX:
        _ASSET_DIGEST_CACHE.pop(next(iter(_ASSET_DIGEST_CACHE)))
    _ASSET_DIGEST_CACHE[key] = (content, digest)
    return digest


_DECODED_ASSET_CACHE: "OrderedDict[int, tuple[bytes, list[Image.Image]]]" = OrderedDict()
_DECODED_ASSET_LIMIT_BYTES = 128 * 1024 * 1024
_DECODED_ASSET_USED_BYTES = 0
_MIN_MIP_EDGE = 64


def _evict_decoded_assets() -> None:
    global _DECODED_ASSET_USED_BYTES

    while _DECODED_ASSET_USED_BYTES > _DECODED_ASSET_LIMIT_BYTES and _DECODED_ASSET_CACHE:
        _key, (_content, levels) = _DECODED_ASSET_CACHE.popitem(last=False)
        _DECODED_ASSET_USED_BYTES -= sum(_image_bytes(level) for level in levels)


def _decoded_levels(content: bytes, opener: Callable[[], Image.Image]) -> list[Image.Image]:
    global _DECODED_ASSET_USED_BYTES

    key = id(content)
    hit = _DECODED_ASSET_CACHE.get(key)
    if hit is not None and hit[0] is content:
        _DECODED_ASSET_CACHE.move_to_end(key)
        return hit[1]

    image = opener()
    levels = [image]
    size = _image_bytes(image)
    if size > _DECODED_ASSET_LIMIT_BYTES:
        # Terlalu besar untuk di-cache; jangan usir seluruh isi cache karenanya.
        return levels
    _DECODED_ASSET_CACHE[key] = (content, levels)
    _DECODED_ASSET_USED_BYTES += size
    _evict_decoded_assets()
    return levels


def decode_asset_once(content: bytes, opener: Callable[[], Image.Image]) -> Image.Image:
    """Decode raster bytes at most once and reuse the decoded image."""

    return _decoded_levels(content, opener)[0]


def display_source(
    content: bytes,
    opener: Callable[[], Image.Image],
    width: int,
    height: int,
) -> Image.Image:
    """Sumber terbaik untuk diperkecil ke ``width`` x ``height``.

    Dua penyebab lag saat hasil BatikBrew (768-1024 px) ada di kanvas:

    1. PNG penuh didekode ulang untuk *setiap* objek di *setiap* langkah zoom.
    2. LANCZOS dari 1024 px menimbang seluruh piksel sumber, dan biayanya
       sebanding dengan luas *sumber* -- bukan luas hasil.

    Fungsi ini menjawab keduanya: hasil dekode disimpan, lalu piramida mipmap
    (1/2, 1/4, ...) dibangun sekali dan dipakai ulang. Perkecilan berikutnya
    berangkat dari level terdekat yang masih >= 2x ukuran target, sehingga
    kualitasnya tetap terjaga dengan biaya jauh lebih kecil.

    Gambar yang dikembalikan dipakai bersama, jadi pemanggil **tidak boleh**
    memodifikasinya di tempat. ``resize``/``rotate``/``crop`` aman karena
    selalu menghasilkan objek baru.
    """

    global _DECODED_ASSET_USED_BYTES

    levels = _decoded_levels(content, opener)
    base = levels[0]
    if width <= 0 or height <= 0:
        return base

    best = base
    for level in levels:
        if level.width >= width * 2 and level.height >= height * 2:
            best = level
        else:
            break

    cached = _DECODED_ASSET_CACHE.get(id(content))
    if cached is None or cached[1] is not levels:
        return best  # aset tidak ter-cache; jangan bangun piramida sekali pakai

    while (
        best.width >= width * 4
        and best.height >= height * 4
        and best.width // 2 >= _MIN_MIP_EDGE
        and best.height // 2 >= _MIN_MIP_EDGE
    ):
        smaller = best.resize(
            (best.width // 2, best.height // 2), Image.Resampling.LANCZOS
        )
        levels.append(smaller)
        _DECODED_ASSET_USED_BYTES += _image_bytes(smaller)
        best = smaller
    _evict_decoded_assets()
    return best


def clear_decoded_asset_cache() -> None:
    global _DECODED_ASSET_USED_BYTES

    _DECODED_ASSET_CACHE.clear()
    _DECODED_ASSET_USED_BYTES = 0


def decoded_asset_cache_stats() -> dict[str, int]:
    return {
        "decoded_count": len(_DECODED_ASSET_CACHE),
        "decoded_levels": sum(len(levels) for _c, levels in _DECODED_ASSET_CACHE.values()),
        "decoded_bytes": _DECODED_ASSET_USED_BYTES,
        "decoded_limit": _DECODED_ASSET_LIMIT_BYTES,
    }


def _gradient_hash(props: dict[str, Any] | None) -> str:
    if props is None:
        return ""
    canonical = str(sorted(props.items()))
    return hashlib.sha1(canonical.encode(), usedforsecurity=False).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Tile cache
# ---------------------------------------------------------------------------


class TileCache:
    """LRU cache for rendered TILE_SIZE×TILE_SIZE Pillow images."""

    def __init__(
        self,
        max_bytes: int = _DEFAULT_TILE_LIMIT,
        *,
        debug: bool = False,
    ) -> None:
        self._max_bytes = max_bytes
        self._debug = debug
        self._store: OrderedDict[TileCacheKey, Image.Image] = OrderedDict()
        self._used_bytes: int = 0
        # Debug stats
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(self, key: TileCacheKey) -> Image.Image | None:
        if key in self._store:
            self._store.move_to_end(key)
            if self._debug:
                self._hits += 1
            return self._store[key]
        if self._debug:
            self._misses += 1
        return None

    def put(self, key: TileCacheKey, image: Image.Image) -> None:
        size = _image_bytes(image)
        if key in self._store:
            self._used_bytes -= _image_bytes(self._store[key])
            del self._store[key]
        self._store[key] = image
        self._store.move_to_end(key)
        self._used_bytes += size
        self._evict()

    def invalidate_project(self, project_revision: int | None = None) -> None:
        """Remove all tiles for a given revision, or all tiles if revision is None."""
        keys_to_remove = [
            k for k in self._store
            if project_revision is None or k.project_revision == project_revision
        ]
        for k in keys_to_remove:
            self._used_bytes -= _image_bytes(self._store[k])
            del self._store[k]

    def clear(self) -> None:
        self._store.clear()
        self._used_bytes = 0

    def debug_stats(self) -> dict[str, Any]:
        return {
            "tile_hits": self._hits,
            "tile_misses": self._misses,
            "tile_count": len(self._store),
            "tile_bytes": self._used_bytes,
            "tile_limit": self._max_bytes,
        }

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _evict(self) -> None:
        while self._used_bytes > self._max_bytes and self._store:
            _key, img = self._store.popitem(last=False)
            self._used_bytes -= _image_bytes(img)


# ---------------------------------------------------------------------------
# Object render cache
# ---------------------------------------------------------------------------


class ObjectRenderCache:
    """LRU cache for fully-prepared object Pillow images."""

    def __init__(
        self,
        max_bytes: int = _DEFAULT_OBJECT_LIMIT,
        *,
        debug: bool = False,
    ) -> None:
        self._max_bytes = max_bytes
        self._debug = debug
        self._store: OrderedDict[ObjectRenderCacheKey, Image.Image] = OrderedDict()
        self._used_bytes: int = 0
        self._hits = 0
        self._misses = 0

    def get(self, key: ObjectRenderCacheKey) -> Image.Image | None:
        if key in self._store:
            self._store.move_to_end(key)
            if self._debug:
                self._hits += 1
            return self._store[key]
        if self._debug:
            self._misses += 1
        return None

    def put(self, key: ObjectRenderCacheKey, image: Image.Image) -> None:
        size = _image_bytes(image)
        if key in self._store:
            self._used_bytes -= _image_bytes(self._store[key])
            del self._store[key]
        self._store[key] = image
        self._store.move_to_end(key)
        self._used_bytes += size
        self._evict()

    def invalidate_object(self, object_id: str) -> None:
        keys_to_remove = [k for k in self._store if k.object_id == object_id]
        for k in keys_to_remove:
            self._used_bytes -= _image_bytes(self._store[k])
            del self._store[k]

    def clear(self) -> None:
        self._store.clear()
        self._used_bytes = 0

    def debug_stats(self) -> dict[str, Any]:
        return {
            "object_hits": self._hits,
            "object_misses": self._misses,
            "object_count": len(self._store),
            "object_bytes": self._used_bytes,
            "object_limit": self._max_bytes,
        }

    def _evict(self) -> None:
        while self._used_bytes > self._max_bytes and self._store:
            _key, img = self._store.popitem(last=False)
            self._used_bytes -= _image_bytes(img)


# ---------------------------------------------------------------------------
# Tile coordinate helpers
# ---------------------------------------------------------------------------


def visible_tile_coords(
    viewport_left: float,
    viewport_top: float,
    viewport_width: float,
    viewport_height: float,
    project_canvas_width: int,
    project_canvas_height: int,
    zoom_scale: float,
    tile_size: int = TILE_SIZE,
    overscan: int = 1,
) -> list[tuple[int, int]]:
    """Return ``(tile_x, tile_y)`` pairs for tiles that intersect the viewport.

    Coordinates are in *tile space* (each unit is *tile_size* project pixels).
    *overscan* extra tiles are added around the viewport border.
    """
    # Convert viewport screen coordinates to project coordinates
    p_left = viewport_left / zoom_scale
    p_top = viewport_top / zoom_scale
    p_right = (viewport_left + viewport_width) / zoom_scale
    p_bottom = (viewport_top + viewport_height) / zoom_scale

    first_tx = max(0, int(math.floor(p_left / tile_size)) - overscan)
    first_ty = max(0, int(math.floor(p_top / tile_size)) - overscan)
    last_tx = min(
        int(math.ceil(project_canvas_width / tile_size)),
        int(math.floor(p_right / tile_size)) + overscan,
    )
    last_ty = min(
        int(math.ceil(project_canvas_height / tile_size)),
        int(math.floor(p_bottom / tile_size)) + overscan,
    )

    return [
        (tx, ty)
        for ty in range(first_ty, last_ty + 1)
        for tx in range(first_tx, last_tx + 1)
    ]


def tile_project_bounds(
    tile_x: int,
    tile_y: int,
    tile_size: int = TILE_SIZE,
) -> tuple[float, float, float, float]:
    """Return the project-space AABB for a tile (left, top, right, bottom)."""
    return (
        tile_x * tile_size,
        tile_y * tile_size,
        (tile_x + 1) * tile_size,
        (tile_y + 1) * tile_size,
    )


__all__ = [
    "TILE_SIZE",
    "ObjectRenderCache",
    "ObjectRenderCacheKey",
    "TileCache",
    "TileCacheKey",
    "tile_project_bounds",
    "visible_tile_coords",
    "zoom_scale_bucket",
    "_asset_digest",
    "_gradient_hash",
]
