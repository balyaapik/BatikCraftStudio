"""Transparent artwork tiles for the bounded viewport renderer.

Viewport tiles contain artwork only.  The Tk canvas owns one separate project
background rectangle, preventing opaque tile-sized blocks from appearing when a
brush stroke triggers a partial viewport refresh.
"""

from __future__ import annotations

from collections.abc import Mapping

from PIL import Image, ImageEnhance

from batikcraft_studio.domain import LayerKind, LayerNodeKind, Project
from batikcraft_studio.imaging.renderer import (
    MissingRasterAssetError,
    _effective_layer_opacity,  # type: ignore[attr-defined]
)
from batikcraft_studio.imaging.safe_viewport_renderer import (
    SCREEN_TILE_SIZE,
    SafeViewportRenderer,
    ScreenTileKey,
    screen_tile_geometry,
)
from batikcraft_studio.imaging.viewport_renderer import (
    _layer_project_bounds,  # type: ignore[attr-defined]
    _prepare_layer_image_zoom,  # type: ignore[attr-defined]
    _render_object_layer_region,  # type: ignore[attr-defined]
    bounds_intersect,
)


def render_project_artwork_region(
    project: Project,
    assets: Mapping[str, bytes],
    *,
    project_bounds: tuple[float, float, float, float],
    zoom_scale: float,
    output_size: tuple[int, int],
) -> Image.Image:
    """Render artwork into a transparent region-sized RGBA image."""

    if zoom_scale <= 0:
        raise ValueError("zoom_scale must be positive")
    out_w = max(1, int(output_size[0]))
    out_h = max(1, int(output_size[1]))
    region_left, region_top, _right, _bottom = project_bounds
    result = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))

    for layer in project.layers:
        if layer.node_kind is LayerNodeKind.GROUP:
            continue
        if not project.is_layer_effectively_visible(layer.layer_id):
            continue

        if layer.objects:
            layer_surface = _render_object_layer_region(
                layer,
                assets,
                project_bounds=project_bounds,
                zoom_scale=zoom_scale,
                region_left=region_left,
                region_top=region_top,
                out_w=out_w,
                out_h=out_h,
            )
            effective_opacity = _effective_layer_opacity(project, layer)
            if effective_opacity < 1.0:
                alpha = layer_surface.getchannel("A")
                layer_surface.putalpha(
                    ImageEnhance.Brightness(alpha).enhance(effective_opacity)
                )
            result.alpha_composite(layer_surface)
            continue

        content: bytes | None = None
        if layer.kind is not LayerKind.SHAPE:
            if layer.asset_ref is None:
                continue
            content = assets.get(layer.asset_ref)
            if content is None:
                raise MissingRasterAssetError(
                    f"Layer {layer.name!r} references missing asset {layer.asset_ref!r}."
                )

        layer_bounds = _layer_project_bounds(layer)
        if not bounds_intersect(layer_bounds, project_bounds):
            continue

        prepared = _prepare_layer_image_zoom(layer, content, zoom_scale=zoom_scale)
        effective_opacity = _effective_layer_opacity(project, layer)
        if effective_opacity != layer.opacity:
            alpha = prepared.getchannel("A")
            inherited = effective_opacity / layer.opacity if layer.opacity else 0.0
            prepared.putalpha(ImageEnhance.Brightness(alpha).enhance(inherited))

        center_x = (layer.transform.x - region_left) * zoom_scale
        center_y = (layer.transform.y - region_top) * zoom_scale
        destination = (
            round(center_x - prepared.width / 2),
            round(center_y - prepared.height / 2),
        )
        result.alpha_composite(prepared, dest=destination)

    return result


class ArtworkViewportRenderer(SafeViewportRenderer):
    """Bounded LRU renderer whose cached tiles preserve transparent artwork alpha."""

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

        image = render_project_artwork_region(
            project,
            assets,
            project_bounds=bounds,
            zoom_scale=zoom_scale,
            output_size=output_size,
        )
        if image.width > SCREEN_TILE_SIZE or image.height > SCREEN_TILE_SIZE:
            raise RuntimeError("viewport renderer produced an oversized artwork tile")

        with self._lock:
            existing = self._cache.pop(key, None)
            if existing is not None:
                self._used_bytes -= self._image_bytes(existing)
            self._cache[key] = image
            self._used_bytes += self._image_bytes(image)
            self._evict_locked()
        return image


__all__ = [
    "ArtworkViewportRenderer",
    "render_project_artwork_region",
]
