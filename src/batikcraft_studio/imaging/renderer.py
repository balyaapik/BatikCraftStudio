"""Pillow renderer for raster-backed and non-destructive shape layers."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageColor, ImageEnhance, UnidentifiedImageError

from batikcraft_studio.domain import Layer, LayerKind, Project
from batikcraft_studio.imaging.shape import ShapeError, render_shape_image


class ProjectRenderError(RuntimeError):
    """Base error for project preview rendering."""


class MissingRasterAssetError(ProjectRenderError):
    """Raised when a visible layer references unavailable raster bytes."""


@dataclass(frozen=True, slots=True)
class RenderedProject:
    """Rendered preview and conversion scale from project to preview pixels."""

    image: Image.Image
    scale: float


def render_project_preview(
    project: Project,
    assets: Mapping[str, bytes],
    *,
    max_width: int,
    max_height: int,
) -> RenderedProject:
    """Render visible raster, paint, and shape layers into a bounded preview."""

    if max_width < 1 or max_height < 1:
        raise ProjectRenderError("Preview dimensions must be positive.")
    scale = min(
        max_width / project.canvas.width,
        max_height / project.canvas.height,
        1.0,
    )
    preview_width = max(1, round(project.canvas.width * scale))
    preview_height = max(1, round(project.canvas.height * scale))
    background = (*ImageColor.getrgb(project.canvas.background_color), 255)
    result = Image.new("RGBA", (preview_width, preview_height), background)

    for layer in project.layers:
        if not layer.visible:
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
        prepared = _prepare_layer_image(layer, content, preview_scale=scale)
        left = round(layer.transform.x * scale - prepared.width / 2)
        top = round(layer.transform.y * scale - prepared.height / 2)
        result.alpha_composite(prepared, dest=(left, top))

    return RenderedProject(image=result, scale=scale)


def transformed_layer_bounds(layer: Layer, *, preview_scale: float = 1.0) -> tuple[float, ...]:
    """Return the axis-aligned transformed layer bounds around its center."""

    width = _positive_property(layer, "pixel_width")
    height = _positive_property(layer, "pixel_height")
    scaled_width = width * abs(layer.transform.scale_x) * preview_scale
    scaled_height = height * abs(layer.transform.scale_y) * preview_scale
    angle = math.radians(layer.transform.rotation_degrees)
    bounds_width = abs(scaled_width * math.cos(angle)) + abs(
        scaled_height * math.sin(angle)
    )
    bounds_height = abs(scaled_width * math.sin(angle)) + abs(
        scaled_height * math.cos(angle)
    )
    center_x = layer.transform.x * preview_scale
    center_y = layer.transform.y * preview_scale
    return (
        center_x - bounds_width / 2,
        center_y - bounds_height / 2,
        center_x + bounds_width / 2,
        center_y + bounds_height / 2,
    )


def point_hits_layer(layer: Layer, x: float, y: float) -> bool:
    """Return whether a project-space point intersects a layer's rotated bounds."""

    left, top, right, bottom = transformed_layer_bounds(layer)
    return left <= x <= right and top <= y <= bottom


def _prepare_layer_image(
    layer: Layer,
    content: bytes | None,
    *,
    preview_scale: float,
) -> Image.Image:
    width = max(
        1,
        round(_positive_property(layer, "pixel_width") * abs(layer.transform.scale_x) * preview_scale),
    )
    height = max(
        1,
        round(
            _positive_property(layer, "pixel_height")
            * abs(layer.transform.scale_y)
            * preview_scale
        ),
    )

    if layer.kind is LayerKind.SHAPE:
        try:
            image = render_shape_image(layer, width, height)
        except ShapeError as exc:
            raise ProjectRenderError(f"Layer {layer.name!r} contains invalid shape data.") from exc
    else:
        if content is None:
            raise MissingRasterAssetError(f"Layer {layer.name!r} has no raster content.")
        try:
            with Image.open(BytesIO(content)) as source:
                image = source.convert("RGBA")
        except (UnidentifiedImageError, OSError) as exc:
            raise ProjectRenderError(
                f"Layer {layer.name!r} contains unreadable image data."
            ) from exc
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
        alpha = ImageEnhance.Brightness(alpha).enhance(layer.opacity)
        image.putalpha(alpha)
    return image


def _positive_property(layer: Layer, key: str) -> float:
    value = layer.properties.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ProjectRenderError(
            f"Layer {layer.name!r} must contain a positive numeric {key!r} property."
        )
    return float(value)
