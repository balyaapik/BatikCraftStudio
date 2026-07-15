"""Viewport-region renderer: renders only the visible project area at zoom scale.

This module provides ``render_project_region`` which renders only the portion
of the project canvas that intersects the requested project-space bounding box.
The output image is approximately ``output_size`` pixels, never larger than
``output_size`` regardless of zoom level.

Architecture
------------
::

    render_project_region(project, assets, project_bounds, zoom_scale, output_size)
        ↳ culls objects/layers outside project_bounds
        ↳ renders each visible object at zoom_scale into a region-sized surface
        ↳ returns a Pillow RGBA image of size output_size

This function is used by the tile engine but is also callable directly for
export-quality regional renders.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from PIL import Image, ImageChops, ImageColor, ImageEnhance

from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectKind,
    Project,
)
from batikcraft_studio.imaging.affine_object import (
    object_axis_aligned_bounds,
    object_shear,
)
from batikcraft_studio.imaging.gradient import apply_gradient_to_image
from batikcraft_studio.imaging.renderer import (
    MissingRasterAssetError,
    ProjectRenderError,
    _apply_centered_shear,  # type: ignore[attr-defined]  # reuse internal helper
    _effective_layer_opacity,  # type: ignore[attr-defined]
    _open_rgba,  # type: ignore[attr-defined]
    _positive_property,  # type: ignore[attr-defined]
)
from batikcraft_studio.imaging.shape import ShapeError, render_shape_image


def bounds_intersect(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    """Return True when two axis-aligned bounding boxes overlap."""
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def render_project_region(
    project: Project,
    assets: Mapping[str, bytes],
    project_bounds: tuple[float, float, float, float],
    zoom_scale: float,
    output_size: tuple[int, int],
) -> Image.Image:
    """Render only the portion of *project* that falls inside *project_bounds*.

    Parameters
    ----------
    project
        The project to render.
    assets
        Mapping of asset_ref → PNG bytes.
    project_bounds
        ``(left, top, right, bottom)`` in project coordinates.  Only objects
        that intersect this region are rendered.
    zoom_scale
        Zoom level (1.0 = 100 %).  Controls the resolution of object images.
    output_size
        ``(width, height)`` of the returned image in pixels.

    Returns
    -------
    Image.Image
        RGBA image of size *output_size* containing the rendered region.
    """
    if zoom_scale <= 0:
        raise ProjectRenderError("zoom_scale must be positive.")
    out_w, out_h = max(1, output_size[0]), max(1, output_size[1])
    px_left, px_top, _px_right, _px_bottom = project_bounds

    bg_color = (*ImageColor.getrgb(project.canvas.background_color), 255)
    result = Image.new("RGBA", (out_w, out_h), bg_color)

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
                region_left=px_left,
                region_top=px_top,
                out_w=out_w,
                out_h=out_h,
            )
            effective_opacity = _effective_layer_opacity(project, layer)
            if effective_opacity < 1.0:
                alpha = layer_surface.getchannel("A")
                layer_surface.putalpha(ImageEnhance.Brightness(alpha).enhance(effective_opacity))
            result.alpha_composite(layer_surface)
            continue

        # Legacy non-object layers
        if layer.kind is not LayerKind.SHAPE:
            if layer.asset_ref is None:
                continue
            content = assets.get(layer.asset_ref)
            if content is None:
                raise MissingRasterAssetError(
                    f"Layer {layer.name!r} references missing asset {layer.asset_ref!r}."
                )
        else:
            content = None

        # Cull: compute AABB of this layer in project space
        layer_bounds = _layer_project_bounds(layer)
        if not bounds_intersect(layer_bounds, project_bounds):
            continue

        prepared = _prepare_layer_image_zoom(layer, content, zoom_scale=zoom_scale)
        effective_opacity = _effective_layer_opacity(project, layer)
        if effective_opacity != layer.opacity:
            alpha = prepared.getchannel("A")
            inherited = effective_opacity / layer.opacity if layer.opacity else 0.0
            prepared.putalpha(ImageEnhance.Brightness(alpha).enhance(inherited))

        # Position in output coordinates
        center_in_region_x = (layer.transform.x - px_left) * zoom_scale
        center_in_region_y = (layer.transform.y - px_top) * zoom_scale
        dest_left = round(center_in_region_x - prepared.width / 2)
        dest_top = round(center_in_region_y - prepared.height / 2)
        result.alpha_composite(prepared, dest=(dest_left, dest_top))

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_object_layer_region(
    layer: Layer,
    assets: Mapping[str, bytes],
    project_bounds: tuple[float, float, float, float],
    zoom_scale: float,
    region_left: float,
    region_top: float,
    out_w: int,
    out_h: int,
) -> Image.Image:
    surface = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    for item in layer.objects:
        if not item.visible:
            continue
        # Viewport culling: skip objects outside the requested region
        obj_bounds = object_axis_aligned_bounds(item)
        if not bounds_intersect(obj_bounds, project_bounds):
            continue

        prepared = _prepare_object_image_zoom(item, assets, zoom_scale=zoom_scale)
        center_in_region_x = (item.transform.x - region_left) * zoom_scale
        center_in_region_y = (item.transform.y - region_top) * zoom_scale
        dest_left = round(center_in_region_x - prepared.width / 2)
        dest_top = round(center_in_region_y - prepared.height / 2)

        if item.kind is ObjectKind.ERASER_STROKE:
            _erase_from_surface(surface, prepared, dest_left, dest_top)
        else:
            surface.alpha_composite(prepared, dest=(dest_left, dest_top))
    return surface


def _prepare_object_image_zoom(
    item: LayerObject,
    assets: Mapping[str, bytes],
    *,
    zoom_scale: float,
) -> Image.Image:
    width = max(1, round(item.bounds.width * abs(item.transform.scale_x) * zoom_scale))
    height = max(1, round(item.bounds.height * abs(item.transform.scale_y) * zoom_scale))

    if item.kind is ObjectKind.SHAPE:
        from batikcraft_studio.domain import LayerKind as LK
        from batikcraft_studio.domain import Transform as T

        legacy_shape = Layer(
            name=item.name,
            kind=LK.SHAPE,
            transform=T(),
            properties={
                **dict(item.properties),
                "pixel_width": item.bounds.width,
                "pixel_height": item.bounds.height,
            },
        )
        try:
            image = render_shape_image(legacy_shape, width, height)
        except ShapeError as exc:
            raise ProjectRenderError(
                f"Object {item.name!r} contains invalid shape data."
            ) from exc
    else:
        if item.asset_ref is None:
            raise MissingRasterAssetError(f"Object {item.name!r} has no raster asset.")
        content = assets.get(item.asset_ref)
        if content is None:
            raise MissingRasterAssetError(
                f"Object {item.name!r} references missing asset {item.asset_ref!r}."
            )
        image = _open_rgba(content, f"Object {item.name!r}")
        image = image.resize((width, height), Image.Resampling.LANCZOS)

    if item.transform.scale_x < 0:
        image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if item.transform.scale_y < 0:
        image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    shear_x, shear_y = object_shear(item)
    if shear_x or shear_y:
        image = _apply_centered_shear(image, shear_x, shear_y)
    if item.transform.rotation_degrees:
        image = image.rotate(
            -item.transform.rotation_degrees,
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )
    fill_mode = item.properties.get("fill_mode", "solid")
    gradient = item.properties.get("gradient")
    if fill_mode in ("linear_gradient", "radial_gradient") and gradient is not None:
        image = apply_gradient_to_image(image, dict(gradient), fill_mode)
    if item.opacity < 1.0:
        alpha = image.getchannel("A")
        image.putalpha(ImageEnhance.Brightness(alpha).enhance(item.opacity))
    return image


def _prepare_layer_image_zoom(
    layer: Layer,
    content: bytes | None,
    *,
    zoom_scale: float,
) -> Image.Image:
    pixel_width = _positive_property(layer, "pixel_width")
    pixel_height = _positive_property(layer, "pixel_height")
    width = max(1, round(pixel_width * abs(layer.transform.scale_x) * zoom_scale))
    height = max(1, round(pixel_height * abs(layer.transform.scale_y) * zoom_scale))
    if layer.kind is LayerKind.SHAPE:
        try:
            image = render_shape_image(layer, width, height)
        except ShapeError as exc:
            raise ProjectRenderError(
                f"Layer {layer.name!r} contains invalid shape data."
            ) from exc
    else:
        if content is None:
            raise MissingRasterAssetError(f"Layer {layer.name!r} has no raster content.")
        image = _open_rgba(content, f"Layer {layer.name!r}")
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    if layer.transform.scale_x < 0:
        image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if layer.transform.scale_y < 0:
        image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    if layer.transform.rotation_degrees:
        image = image.rotate(
            -layer.transform.rotation_degrees,
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )
    if layer.opacity < 1.0:
        alpha = image.getchannel("A")
        image.putalpha(ImageEnhance.Brightness(alpha).enhance(layer.opacity))
    return image


def _layer_project_bounds(
    layer: Layer,
) -> tuple[float, float, float, float]:
    """Return the project-space AABB of a single non-object layer."""
    try:
        pixel_width = _positive_property(layer, "pixel_width")
        pixel_height = _positive_property(layer, "pixel_height")
    except ProjectRenderError:
        return (-1e9, -1e9, 1e9, 1e9)
    sw = pixel_width * abs(layer.transform.scale_x)
    sh = pixel_height * abs(layer.transform.scale_y)
    angle = math.radians(layer.transform.rotation_degrees)
    bw = abs(sw * math.cos(angle)) + abs(sh * math.sin(angle))
    bh = abs(sw * math.sin(angle)) + abs(sh * math.cos(angle))
    cx, cy = layer.transform.x, layer.transform.y
    return (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)


def _erase_from_surface(
    surface: Image.Image,
    eraser: Image.Image,
    left: int,
    top: int,
) -> None:
    mask = Image.new("L", surface.size, 0)
    mask.paste(eraser.getchannel("A"), (left, top))
    surface.putalpha(ImageChops.subtract(surface.getchannel("A"), mask))


__all__ = [
    "bounds_intersect",
    "render_project_region",
]
