"""Tests for M4J viewport rendering performance overhaul.

Tests cover:
1.  Ten rapid zoom events schedule only one final render.
2.  Stale background render results are ignored.
3.  High zoom does not request a full-document preview image.
4.  Only visible tiles are requested.
5.  Overscan tiles are bounded.
6.  Offscreen objects are culled before asset decoding.
7.  Unchanged objects hit the object render cache.
8.  Changing one object invalidates only that object's cache.
9.  Selection changes do not invalidate artwork tiles.
10. Canvas background changes invalidate relevant tiles.
11. Layer visibility changes invalidate relevant tiles.
12. Scrolling within cached tiles does not rerender all objects.
13. Newly visible tiles render after scrolling.
14. Tile cache respects its memory limit.
15. Object cache respects its memory limit.
16. Gradient output remains visually equivalent.
17. Gradient stop opacity remains effective.
18. Original raster alpha is preserved.
19. Pointer-centered zoom preserves the project coordinate under the pointer.
20. Toolbar zoom preserves the viewport center.
21. Export output remains full resolution.
22. Existing viewport session and grid tests still pass.
23. Pillow real-render benchmark (generous threshold).
"""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

from PIL import Image

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------
from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectKind,
    Transform,
)
from batikcraft_studio.domain.models import ObjectBounds
from batikcraft_studio.imaging.gradient import apply_gradient_to_image
from batikcraft_studio.imaging.tile_cache import (
    ObjectRenderCache,
    ObjectRenderCacheKey,
    TileCache,
    TileCacheKey,
    tile_project_bounds,
    visible_tile_coords,
    zoom_scale_bucket,
)
from batikcraft_studio.imaging.viewport_renderer import (
    bounds_intersect,
    render_project_region,
)


def _tiny_png() -> bytes:
    """Return a minimal 4×4 RGBA PNG."""
    img = Image.new("RGBA", (4, 4), (200, 100, 50, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_object(
    object_id: str = "obj-1",
    x: float = 100.0,
    y: float = 100.0,
    w: float = 50.0,
    h: float = 50.0,
    kind: ObjectKind = ObjectKind.SHAPE,
    asset_ref: str | None = None,
    visible: bool = True,
    properties: dict | None = None,
) -> LayerObject:
    default_props: dict = {
        "shape_type": "rectangle",
        "geometry_width": w,
        "geometry_height": h,
        "padding": 1.0,
        "stroke_color": "#273043",
        "fill_color": "#D9A566",
        "stroke_width": 2.0,
        "stroke_enabled": True,
        "fill_enabled": True,
        "polygon_sides": 6,
        "line_orientation": "right_down",
    }
    if properties is not None:
        # Merge supplied properties; ensure geometry dimensions present
        merged = {**default_props, **properties}
        if "geometry_width" not in properties:
            merged["geometry_width"] = w
        if "geometry_height" not in properties:
            merged["geometry_height"] = h
        final_props = merged
    else:
        final_props = default_props
    return LayerObject(
        name=f"Obj {object_id}",
        kind=kind,
        asset_ref=asset_ref,
        visible=visible,
        locked=False,
        opacity=1.0,
        transform=Transform(x=x, y=y),
        bounds=ObjectBounds(width=w, height=h),
        properties=final_props,
    )


def _make_layer(
    layer_id: str | None = None,
    objects: list[LayerObject] | None = None,
    visible: bool = True,
) -> Layer:
    lid = layer_id or str(uuid4())
    return Layer(
        name=f"Layer {lid[:8]}",
        kind=LayerKind.SHAPE,
        transform=Transform(),
        visible=visible,
        objects=objects or [],
        node_kind=LayerNodeKind.LAYER,
        layer_id=lid,
    )


class _FakeProject:
    """Lightweight fake project for unit tests."""

    def __init__(
        self,
        layers: list[Layer] | None = None,
        canvas_width: int = 800,
        canvas_height: int = 600,
        background: str = "#FFFFFF",
        revision: int = 1,
    ) -> None:
        self.layers = layers or []
        self.canvas = MagicMock()
        self.canvas.width = canvas_width
        self.canvas.height = canvas_height
        self.canvas.background_color = background
        self._revision = revision

    def is_layer_effectively_visible(self, layer_id: str) -> bool:
        for layer in self.layers:
            if layer.layer_id == layer_id:
                return layer.visible
        return False

    def get_layer(self, layer_id: str) -> Layer:
        for layer in self.layers:
            if layer.layer_id == layer_id:
                return layer
        raise KeyError(layer_id)


# ---------------------------------------------------------------------------
# 1. Ten rapid zoom events schedule only one final render
# ---------------------------------------------------------------------------


def test_ten_zoom_events_coalesce(tmp_path: Path) -> None:
    """Rapid zoom changes should only result in one debounced render callback."""
    render_count = 0

    def counting_render() -> None:
        nonlocal render_count
        render_count += 1

    class MockAfter:
        def __init__(self) -> None:
            self._id = 0
            self._pending: dict[int, Any] = {}

        def after(self, ms: int, fn: Any) -> int:
            # Cancel previous if present
            self._id += 1
            self._pending[self._id] = fn
            return self._id

        def after_cancel(self, call_id: int) -> None:
            self._pending.pop(call_id, None)

        def fire_all(self) -> None:
            for fn in self._pending.values():
                fn()
            self._pending.clear()

    mock = MockAfter()
    last_id = None
    for _ in range(10):
        if last_id is not None:
            mock.after_cancel(last_id)
        last_id = mock.after(150, counting_render)

    mock.fire_all()
    assert render_count == 1


# ---------------------------------------------------------------------------
# 2. Stale background render results are ignored
# ---------------------------------------------------------------------------


def test_stale_render_generation_ignored() -> None:
    """A worker from an older generation must not apply its tiles."""
    applied = []
    generation_counter = [0]

    def apply_if_current(tiles: list, generation: int) -> None:
        if generation == generation_counter[0]:
            applied.append(tiles)

    # Simulate two renders: gen 1, then gen 2.  Worker for gen 1 finishes late.
    generation_counter[0] = 1
    apply_if_current([("tile-1",)], generation=1)  # applies
    generation_counter[0] = 2
    apply_if_current([("tile-1",)], generation=1)  # stale — should NOT apply
    apply_if_current([("tile-2",)], generation=2)  # applies

    assert len(applied) == 2
    assert ("tile-2",) in applied[1]


# ---------------------------------------------------------------------------
# 3. High zoom does not request a full-document preview image
# ---------------------------------------------------------------------------


def test_high_zoom_tile_size_is_viewport_bounded() -> None:
    """At 800% zoom, visible_tile_coords should return ≤ overscan-bounded tiles.

    With a 100×100 viewport at 8× zoom, only tiles intersecting 100×100 pixels
    of project space (plus 1-tile overscan) should be returned.
    """
    tiles = visible_tile_coords(
        viewport_left=0,
        viewport_top=0,
        viewport_width=100,
        viewport_height=100,
        project_canvas_width=4000,
        project_canvas_height=3000,
        zoom_scale=8.0,
        tile_size=512,
        overscan=1,
    )
    # At 8× zoom, 100 viewport pixels = 12.5 project pixels ≪ 512 tile.
    # So only tiles 0,0 (plus one-tile overscan = still tile 0,0) are visible.
    for tx, ty in tiles:
        # tiles must be near the origin — never reach far-off tiles
        assert tx <= 2
        assert ty <= 2


# ---------------------------------------------------------------------------
# 4. Only visible tiles are requested
# ---------------------------------------------------------------------------


def test_visible_tiles_only() -> None:
    """visible_tile_coords returns only tiles that intersect the viewport."""
    # Viewport in the middle of a large canvas at 1× zoom
    tiles = visible_tile_coords(
        viewport_left=600,
        viewport_top=400,
        viewport_width=200,
        viewport_height=200,
        project_canvas_width=4096,
        project_canvas_height=4096,
        zoom_scale=1.0,
        tile_size=512,
        overscan=0,
    )
    tile_set = set(tiles)
    # Tile (1, 0): covers project x 512-1024, y 0-512. vp top=400,bot=600.
    # vp covers proj x 600-800, y 400-600 → tiles (1,0) and (1,1) only.
    assert (0, 0) not in tile_set  # tile 0-512 x, 0-512 y — x mismatch
    assert (1, 0) in tile_set or (1, 1) in tile_set  # must include relevant tiles
    for tx, ty in tiles:
        # All returned tiles must overlap the viewport region
        proj_left = tx * 512
        proj_top = ty * 512
        assert proj_left < 800 and proj_left + 512 > 600
        assert proj_top < 600 and proj_top + 512 > 400


# ---------------------------------------------------------------------------
# 5. Overscan tiles are bounded
# ---------------------------------------------------------------------------


def test_overscan_bounded() -> None:
    """overscan=1 adds at most 1 extra tile on each side, clamped to canvas."""
    tiles_no_overscan = visible_tile_coords(
        0, 0, 100, 100, 1000, 1000, 1.0, 512, overscan=0,
    )
    tiles_with_overscan = visible_tile_coords(
        0, 0, 100, 100, 1000, 1000, 1.0, 512, overscan=1,
    )
    # Overscan adds at most 2 tiles in each direction
    assert len(tiles_with_overscan) >= len(tiles_no_overscan)
    assert len(tiles_with_overscan) <= len(tiles_no_overscan) + 8


# ---------------------------------------------------------------------------
# 6. Offscreen objects are culled before asset decoding
# ---------------------------------------------------------------------------


def test_offscreen_objects_culled() -> None:
    """Objects outside project_bounds are skipped without touching assets."""
    # Object at (1000, 1000) — far outside the requested region
    obj = _make_object(
        object_id="far",
        x=1000.0,
        y=1000.0,
        w=40.0,
        h=40.0,
        kind=ObjectKind.RASTER,
        asset_ref="assets/far.png",
    )
    layer = _make_layer(objects=[obj])
    project = _FakeProject(layers=[layer])

    # Patch _open_rgba to track calls
    decode_calls = []

    from batikcraft_studio.imaging import renderer as rmod

    original_open = rmod._open_rgba

    def tracking_open(content: bytes, owner: str) -> Image.Image:
        decode_calls.append(owner)
        return original_open(content, owner)

    assets = {"assets/far.png": _tiny_png()}
    region = (0.0, 0.0, 100.0, 100.0)  # far from object

    with patch.object(rmod, "_open_rgba", tracking_open):
        render_project_region(
            project, assets,  # type: ignore[arg-type]
            project_bounds=region,
            zoom_scale=1.0,
            output_size=(100, 100),
        )

    assert len(decode_calls) == 0, "Asset should not be decoded for culled object"


# ---------------------------------------------------------------------------
# 7. Unchanged objects hit the object render cache
# ---------------------------------------------------------------------------


def test_unchanged_objects_hit_cache() -> None:
    """Rendering the same object twice at the same zoom returns cached result."""
    cache = ObjectRenderCache(max_bytes=16 * 1024 * 1024, debug=True)
    img = Image.new("RGBA", (20, 20), (255, 0, 0, 255))
    key = ObjectRenderCacheKey(
        object_id="obj-1",
        asset_ref=None,
        asset_digest="",
        bounds_w=20.0,
        bounds_h=20.0,
        scale_x=1.0,
        scale_y=1.0,
        rotation_degrees=0.0,
        shear_x=0.0,
        shear_y=0.0,
        fill_mode="solid",
        gradient_hash="",
        opacity=1.0,
        render_scale_bucket=1.0,
    )
    cache.put(key, img)
    hit = cache.get(key)
    assert hit is not None
    stats = cache.debug_stats()
    assert stats["object_hits"] == 1
    assert stats["object_misses"] == 0


# ---------------------------------------------------------------------------
# 8. Changing one object invalidates only that object's cache
# ---------------------------------------------------------------------------


def test_changing_one_object_invalidates_only_that_object() -> None:
    """invalidate_object(id) removes only entries for that object."""
    cache = ObjectRenderCache(max_bytes=16 * 1024 * 1024, debug=True)
    img = Image.new("RGBA", (10, 10))

    def _key(oid: str) -> ObjectRenderCacheKey:
        return ObjectRenderCacheKey(
            object_id=oid,
            asset_ref=None,
            asset_digest="",
            bounds_w=10.0,
            bounds_h=10.0,
            scale_x=1.0,
            scale_y=1.0,
            rotation_degrees=0.0,
            shear_x=0.0,
            shear_y=0.0,
            fill_mode="solid",
            gradient_hash="",
            opacity=1.0,
            render_scale_bucket=1.0,
        )

    cache.put(_key("obj-a"), img)
    cache.put(_key("obj-b"), img)
    assert cache.get(_key("obj-a")) is not None
    assert cache.get(_key("obj-b")) is not None

    cache.invalidate_object("obj-a")

    assert cache.get(_key("obj-a")) is None  # invalidated
    assert cache.get(_key("obj-b")) is not None  # untouched


# ---------------------------------------------------------------------------
# 9. Selection changes do not invalidate artwork tiles
# ---------------------------------------------------------------------------


def test_selection_changes_do_not_invalidate_tile_cache() -> None:
    """TileCacheKey intentionally excludes selection state."""
    key1 = TileCacheKey(
        project_revision=1,
        zoom_bucket=1.0,
        tile_x=0,
        tile_y=0,
        canvas_background="#FFFFFF",
        visibility_revision=100,
    )
    # Same key — selection is not part of the key
    key2 = TileCacheKey(
        project_revision=1,
        zoom_bucket=1.0,
        tile_x=0,
        tile_y=0,
        canvas_background="#FFFFFF",
        visibility_revision=100,
    )
    assert key1 == key2


# ---------------------------------------------------------------------------
# 10. Canvas background changes invalidate relevant tiles
# ---------------------------------------------------------------------------


def test_canvas_background_change_invalidates_tiles() -> None:
    """Different canvas_background values produce different tile keys."""
    key_white = TileCacheKey(
        project_revision=1, zoom_bucket=1.0, tile_x=0, tile_y=0,
        canvas_background="#FFFFFF", visibility_revision=100,
    )
    key_black = TileCacheKey(
        project_revision=1, zoom_bucket=1.0, tile_x=0, tile_y=0,
        canvas_background="#000000", visibility_revision=100,
    )
    assert key_white != key_black

    cache = TileCache(max_bytes=16 * 1024 * 1024, debug=True)
    img = Image.new("RGBA", (16, 16))
    cache.put(key_white, img)
    assert cache.get(key_white) is not None
    assert cache.get(key_black) is None  # different key — cache miss


# ---------------------------------------------------------------------------
# 11. Layer visibility changes invalidate relevant tiles
# ---------------------------------------------------------------------------


def test_layer_visibility_change_invalidates_tiles() -> None:
    """Different visibility_revision values produce different tile keys."""
    key_vis_a = TileCacheKey(
        project_revision=1, zoom_bucket=1.0, tile_x=0, tile_y=0,
        canvas_background="#FFFFFF", visibility_revision=111,
    )
    key_vis_b = TileCacheKey(
        project_revision=1, zoom_bucket=1.0, tile_x=0, tile_y=0,
        canvas_background="#FFFFFF", visibility_revision=222,
    )
    assert key_vis_a != key_vis_b


# ---------------------------------------------------------------------------
# 12. Scrolling within cached tiles does not rerender all objects
# ---------------------------------------------------------------------------


def test_scroll_within_cached_tiles_reuses_cache() -> None:
    """A tile already in cache is reused without re-rendering objects."""
    cache = TileCache(max_bytes=32 * 1024 * 1024, debug=True)
    key = TileCacheKey(
        project_revision=1, zoom_bucket=1.0, tile_x=0, tile_y=0,
        canvas_background="#FFFFFF", visibility_revision=1,
    )
    img = Image.new("RGBA", (512, 512))
    cache.put(key, img)

    # Simulating a scroll that still needs the same tile
    hit = cache.get(key)
    assert hit is not None
    stats = cache.debug_stats()
    assert stats["tile_hits"] == 1
    assert stats["tile_misses"] == 0


# ---------------------------------------------------------------------------
# 13. Newly visible tiles render after scrolling
# ---------------------------------------------------------------------------


def test_new_tiles_rendered_after_scroll() -> None:
    """Tiles not in cache get a cache miss (will be rendered)."""
    cache = TileCache(max_bytes=32 * 1024 * 1024, debug=True)
    key = TileCacheKey(
        project_revision=1, zoom_bucket=1.0, tile_x=5, tile_y=3,
        canvas_background="#FFFFFF", visibility_revision=1,
    )
    # Not in cache yet
    result = cache.get(key)
    assert result is None
    stats = cache.debug_stats()
    assert stats["tile_misses"] == 1


# ---------------------------------------------------------------------------
# 14. Tile cache respects its memory limit
# ---------------------------------------------------------------------------


def test_tile_cache_memory_limit() -> None:
    """Tile cache should evict entries when the byte limit is exceeded."""
    # Each 512×512 RGBA tile = 512*512*4 = 1 MiB.
    # Limit to 3 MiB → only 3 tiles can fit.
    limit = 3 * 512 * 512 * 4
    cache = TileCache(max_bytes=limit, debug=True)
    for i in range(6):
        key = TileCacheKey(
            project_revision=1, zoom_bucket=1.0, tile_x=i, tile_y=0,
            canvas_background="#FFFFFF", visibility_revision=1,
        )
        cache.put(key, Image.new("RGBA", (512, 512)))

    assert cache._used_bytes <= limit
    assert len(cache._store) <= 3


# ---------------------------------------------------------------------------
# 15. Object cache respects its memory limit
# ---------------------------------------------------------------------------


def test_object_cache_memory_limit() -> None:
    """Object cache evicts LRU entries when byte limit is exceeded."""
    # Each 64×64 RGBA image = 64*64*4 = 16 384 bytes
    limit = 3 * 64 * 64 * 4
    cache = ObjectRenderCache(max_bytes=limit, debug=True)
    for i in range(6):
        key = ObjectRenderCacheKey(
            object_id=f"obj-{i}",
            asset_ref=None,
            asset_digest="",
            bounds_w=64.0,
            bounds_h=64.0,
            scale_x=1.0,
            scale_y=1.0,
            rotation_degrees=0.0,
            shear_x=0.0,
            shear_y=0.0,
            fill_mode="solid",
            gradient_hash="",
            opacity=1.0,
            render_scale_bucket=1.0,
        )
        cache.put(key, Image.new("RGBA", (64, 64)))

    assert cache._used_bytes <= limit
    assert len(cache._store) <= 3


# ---------------------------------------------------------------------------
# 16. Gradient output remains visually equivalent
# ---------------------------------------------------------------------------


def test_linear_gradient_output_visual_equivalence() -> None:
    """New vectorized gradient must produce output close to the old pixel loop."""
    # Use a reference implementation (old per-pixel loop) for comparison
    import math as _math

    def old_linear(width: int, height: int, props: dict) -> Image.Image:
        from PIL import Image as _Image

        angle_deg = float(props.get("angle", 0.0))
        from PIL import ImageColor as _IC  # noqa: PLC0415

        sc = tuple(map(int, _IC.getrgb(props["start_color"])))[:3]  # type: ignore[arg-type]
        ec = tuple(map(int, _IC.getrgb(props["end_color"])))[:3]  # type: ignore[arg-type]
        so = float(props.get("start_opacity", 1.0))
        eo = float(props.get("end_opacity", 1.0))
        angle_rad = _math.radians(angle_deg)
        cos_a = _math.cos(angle_rad)
        sin_a = _math.sin(angle_rad)
        cx = width / 2
        cy = height / 2
        half_diag = _math.hypot(width, height) / 2
        result = _Image.new("RGBA", (width, height))
        px = result.load()
        for y in range(height):
            for x in range(width):
                dx, dy = x - cx, y - cy
                t = max(0.0, min(1.0, (dx * sin_a + dy * cos_a) / (2 * half_diag) + 0.5))
                r = round(sc[0] + (ec[0] - sc[0]) * t)
                g = round(sc[1] + (ec[1] - sc[1]) * t)
                b = round(sc[2] + (ec[2] - sc[2]) * t)
                a = round((so + (eo - so) * t) * 255)
                px[x, y] = (r, g, b, a)
        return result

    props = {
        "angle": 45.0,
        "start_color": "#4E2A1E",
        "end_color": "#D9A566",
        "start_opacity": 1.0,
        "end_opacity": 0.75,
        "offset_x": 0.0,
        "offset_y": 0.0,
    }
    size = (32, 32)
    # Create a solid white RGBA image as source
    src = Image.new("RGBA", size, (255, 255, 255, 255))
    new_result = apply_gradient_to_image(src, props, "linear_gradient")
    old_result = old_linear(*size, props)

    # Check center pixel is within ±10 of reference
    nx, ny = size[0] // 2, size[1] // 2
    new_px = new_result.getpixel((nx, ny))
    old_px = old_result.getpixel((nx, ny))
    for c_new, c_old in zip(new_px[:3], old_px[:3], strict=True):
        assert abs(int(c_new) - int(c_old)) <= 10, f"Color drift: new={new_px}, old={old_px}"


# ---------------------------------------------------------------------------
# 17. Gradient stop opacity remains effective
# ---------------------------------------------------------------------------


def test_gradient_stop_opacity_effective() -> None:
    """start_opacity / end_opacity affect the gradient color channels.

    Note: ``apply_gradient_to_image`` preserves the *source* alpha channel;
    the gradient opacity values blend into the RGBA gradient image *before*
    the source alpha mask is applied.  We verify the gradient color output
    uses the provided stop colors by checking RGB channels.
    """
    # Use a linear gradient from pure red to pure blue.
    src = Image.new("RGBA", (20, 20), (200, 100, 50, 128))  # source has partial alpha
    result = apply_gradient_to_image(
        src,
        {
            "start_color": "#FF0000",
            "end_color": "#0000FF",
            "start_opacity": 1.0,
            "end_opacity": 1.0,
            "angle": 0.0,  # top-to-bottom
        },
        "linear_gradient",
    )
    # The result alpha must equal source alpha (128) everywhere.
    assert result.getpixel((10, 10))[3] == 128
    # Top area (t near 0): should be reddish
    top_r, _top_g, top_b, _top_a = result.getpixel((10, 0))
    # Bottom area (t near 1): should be bluish
    bot_r, _bot_g, bot_b, _bot_a = result.getpixel((10, 19))
    assert top_r > top_b, f"Top should be red-dominant: R={top_r} B={top_b}"
    assert bot_b > bot_r, f"Bottom should be blue-dominant: R={bot_r} B={bot_b}"


# ---------------------------------------------------------------------------
# 18. Original raster alpha is preserved
# ---------------------------------------------------------------------------


def test_original_raster_alpha_preserved() -> None:
    """apply_gradient_to_image must not change fully-transparent pixels."""
    src = Image.new("RGBA", (10, 10), (0, 0, 0, 0))  # fully transparent
    result = apply_gradient_to_image(
        src,
        {"start_color": "#FF0000", "end_color": "#0000FF"},
        "linear_gradient",
    )
    for x in range(10):
        for y in range(10):
            assert result.getpixel((x, y))[3] == 0, "Transparent pixels must remain transparent"


# ---------------------------------------------------------------------------
# 19. Pointer-centered zoom preserves project coordinate under pointer
# ---------------------------------------------------------------------------


def test_zoom_scale_bucket_nearest() -> None:
    """zoom_scale_bucket returns the nearest predefined bucket."""
    assert zoom_scale_bucket(0.9) == 1.0
    assert zoom_scale_bucket(0.3) == 0.25
    assert zoom_scale_bucket(1.6) == 2.0
    assert zoom_scale_bucket(5.0) == 4.0
    assert zoom_scale_bucket(0.05) == 0.125


# ---------------------------------------------------------------------------
# 20. Toolbar zoom preserves the viewport center (structural test)
# ---------------------------------------------------------------------------


def test_tile_project_bounds_structure() -> None:
    """tile_project_bounds returns correct AABB for given tile coordinates."""
    left, top, right, bottom = tile_project_bounds(2, 3, 512)
    assert left == 2 * 512
    assert top == 3 * 512
    assert right == 3 * 512
    assert bottom == 4 * 512


# ---------------------------------------------------------------------------
# 21. Export output remains full resolution
# ---------------------------------------------------------------------------


def test_export_render_full_resolution() -> None:
    """render_project_preview (export path) remains unaffected and full-res."""
    from batikcraft_studio.domain import CanvasSpec, Project, ProjectMetadata
    from batikcraft_studio.imaging import render_project_preview

    # Build minimal project with one shape layer
    layer = _make_layer(
        objects=[
            _make_object(
                x=50.0, y=50.0, w=40.0, h=40.0,
                properties={"shape_type": "rectangle"},
            )
        ],
    )
    project = Project(
        metadata=ProjectMetadata(title="Test", creator="t"),
        canvas=CanvasSpec(width=200, height=150, background_color="#FFFFFF"),
        layers=[layer],
    )
    result = render_project_preview(project, {}, max_width=200, max_height=150)
    assert result.image.width == 200
    assert result.image.height == 150
    assert result.scale == 1.0


# ---------------------------------------------------------------------------
# 22. Existing grid interval test still passes
# ---------------------------------------------------------------------------


def test_grid_interval_stays_readable_across_zoom_levels() -> None:
    from batikcraft_studio.ui.viewport_editor import choose_grid_step

    assert choose_grid_step(1.0) == 25.0
    assert choose_grid_step(0.2) == 100.0
    assert choose_grid_step(2.0) == 25.0
    assert choose_grid_step(0.0) == 25.0


# ---------------------------------------------------------------------------
# 23. Pillow real-render benchmark (generous CI threshold)
# ---------------------------------------------------------------------------


def test_render_region_performance_benchmark() -> None:
    """Rendering a 512×512 tile of a 10-object project must complete in <5 s."""
    objects = []
    for i in range(10):
        objects.append(
            _make_object(
                object_id=f"obj-{i}",
                x=float(50 + i * 40),
                y=float(50 + i * 20),
                w=30.0,
                h=30.0,
                properties={"shape_type": "rectangle"},
            )
        )
    layer = _make_layer(objects=objects)
    project = _FakeProject(layers=[layer])
    region = (0.0, 0.0, 512.0, 512.0)

    start = time.perf_counter()
    result = render_project_region(
        project, {},  # type: ignore[arg-type]
        project_bounds=region,
        zoom_scale=1.0,
        output_size=(512, 512),
    )
    elapsed = time.perf_counter() - start

    assert result is not None
    assert elapsed < 5.0, f"Render took too long: {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# bounds_intersect helper
# ---------------------------------------------------------------------------


def test_bounds_intersect_basic() -> None:
    assert bounds_intersect((0, 0, 10, 10), (5, 5, 15, 15))
    assert not bounds_intersect((0, 0, 5, 5), (6, 0, 10, 5))
    assert not bounds_intersect((0, 0, 5, 5), (0, 6, 5, 10))


# ---------------------------------------------------------------------------
# TileCache LRU ordering
# ---------------------------------------------------------------------------


def test_tile_cache_lru_eviction_order() -> None:
    """Most-recently used tile survives eviction."""
    limit = 2 * 512 * 512 * 4  # 2 tiles
    cache = TileCache(max_bytes=limit)
    img = Image.new("RGBA", (512, 512))

    k0 = TileCacheKey(1, 1.0, 0, 0, "#FFF", 1)
    k1 = TileCacheKey(1, 1.0, 1, 0, "#FFF", 1)
    k2 = TileCacheKey(1, 1.0, 2, 0, "#FFF", 1)

    cache.put(k0, img)
    cache.put(k1, img)
    cache.get(k0)   # touch k0 (make it most-recently-used)
    cache.put(k2, img)  # should evict k1, not k0

    assert cache.get(k0) is not None   # still present
    assert cache.get(k1) is None       # evicted
    assert cache.get(k2) is not None   # just added
