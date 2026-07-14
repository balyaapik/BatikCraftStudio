"""Pillow renderer for legacy layers and object-capable layer containers."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageChops, ImageColor, ImageEnhance, UnidentifiedImageError

from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectKind,
    Project,
    Transform,
)
from batikcraft_studio.imaging.shape import ShapeError, render_shape_image


class ProjectRenderError(RuntimeError):
    """Base error for project preview rendering."""


class MissingRasterAssetError(ProjectRenderError):
    """Raised when a visible layer or object references unavailable raster bytes."""


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
    """Render visible layer containers, objects, and legacy layers."""

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
        if layer.node_kind is LayerNodeKind.GROUP:
            continue
        if not project.is_layer_effectively_visible(layer.layer_id):
            continue
        if layer.objects:
            layer_surface = _render_object_layer(
                project,
                layer,
                assets,
                preview_width=preview_width,
                preview_height=preview_height,
                preview_scale=scale,
            )
            effective_opacity = _effective_layer_opacity(project, layer)
            if effective_opacity < 1.0:
                alpha = layer_surface.getchannel("A")
                alpha = ImageEnhance.Brightness(alpha).enhance(effective_opacity)
                layer_surface.putalpha(alpha)
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
        prepared = _prepare_layer_image(layer, content, preview_scale=scale)
        effective_opacity = _effective_layer_opacity(project, layer)
        if effective_opacity != layer.opacity:
            alpha = prepared.getchannel("A")
            inherited = effective_opacity / layer.opacity if layer.opacity else 0.0
            prepared.putalpha(ImageEnhance.Brightness(alpha).enhance(inherited))
        left = round(layer.transform.x * scale - prepared.width / 2)
        top = round(layer.transform.y * scale - prepared.height / 2)
        result.alpha_composite(prepared, dest=(left, top))

    return RenderedProject(image=result, scale=scale)


def transformed_object_bounds(
    item: LayerObject,
    *,
    preview_scale: float = 1.0,
) -> tuple[float, float, float, float]:
    """Return an object's axis-aligned transformed bounds around its center."""

    return _transformed_bounds(
        width=item.bounds.width,
        height=item.bounds.height,
        transform=item.transform,
        preview_scale=preview_scale,
    )


def point_hits_object(item: LayerObject, x: float, y: float) -> bool:
    """Return whether a project-space point intersects an object's rotated bounds."""

    left, top, right, bottom = transformed_object_bounds(item)
    return left <= x <= right and top <= y <= bottom


def transformed_layer_bounds(
    layer: Layer,
    *,
    preview_scale: float = 1.0,
) -> tuple[float, float, float, float]:
    """Return bounds for a legacy layer or the union of its visible objects."""

    visible_objects = [item for item in layer.objects if item.visible]
    if visible_objects:
        bounds = [
            transformed_object_bounds(item, preview_scale=preview_scale)
            for item in visible_objects
        ]
        return (
            min(value[0] for value in bounds),
            min(value[1] for value in bounds),
            max(value[2] for value in bounds),
            max(value[3] for value in bounds),
        )
    width = _positive_property(layer, "pixel_width")
    height = _positive_property(layer, "pixel_height")
    return _transformed_bounds(
        width=width,
        height=height,
        transform=layer.transform,
        preview_scale=preview_scale,
    )


def point_hits_layer(layer: Layer, x: float, y: float) -> bool:
    left, top, right, bottom = transformed_layer_bounds(layer)
    return left <= x <= right and top <= y <= bottom


def _render_object_layer(
    project: Project,
    layer: Layer,
    assets: Mapping[str, bytes],
    *,
    preview_width: int,
    preview_height: int,
    preview_scale: float,
) -> Image.Image:
    surface = Image.new("RGBA", (preview_width, preview_height), (0, 0, 0, 0))
    for item in layer.objects:
        if not item.visible:
            continue
        prepared = _prepare_object_image(item, assets, preview_scale=preview_scale)
        left = round(item.transform.x * preview_scale - prepared.width / 2)
        top = round(item.transform.y * preview_scale - prepared.height / 2)
        if item.kind is ObjectKind.ERASER_STROKE:
            _erase_from_surface(surface, prepared, left, top)
        else:
            surface.alpha_composite(prepared, dest=(left, top))
    return surface


def _prepare_object_image(
    item: LayerObject,
    assets: Mapping[str, bytes],
    *,
    preview_scale: float,
) -> Image.Image:
    width = max(
        1,
        round(item.bounds.width * abs(item.transform.scale_x) * preview_scale),
    )
    height = max(
        1,
        round(item.bounds.height * abs(item.transform.scale_y) * preview_scale),
    )
    if item.kind is ObjectKind.SHAPE:
        legacy_shape = Layer(
            name=item.name,
            kind=LayerKind.SHAPE,
            transform=Transform(),
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
    if item.transform.rotation_degrees:
        image = image.rotate(
            -item.transform.rotation_degrees,
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )
    if item.opacity < 1.0:
        alpha = image.getchannel("A")
        image.putalpha(ImageEnhance.Brightness(alpha).enhance(item.opacity))
    return image


def _erase_from_surface(
    surface: Image.Image,
    eraser: Image.Image,
    left: int,
    top: int,
) -> None:
    """Subtract an eraser object's alpha from prior objects in its layer."""

    mask = Image.new("L", surface.size, 0)
    mask.paste(eraser.getchannel("A"), (left, top))
    alpha = ImageChops.subtract(surface.getchannel("A"), mask)
    surface.putalpha(alpha)


def _effective_layer_opacity(project: Project, layer: Layer) -> float:
    opacity = layer.opacity
    parent_id = layer.parent_id
    visited: set[str] = set()
    while parent_id is not None:
        if parent_id in visited:
            return 0.0
        visited.add(parent_id)
        parent = project.get_layer(parent_id)
        opacity *= parent.opacity
        parent_id = parent.parent_id
    return opacity


def _prepare_layer_image(
    layer: Layer,
    content: bytes | None,
    *,
    preview_scale: float,
) -> Image.Image:
    pixel_width = _positive_property(layer, "pixel_width")
    pixel_height = _positive_property(layer, "pixel_height")
    width = max(1, round(pixel_width * abs(layer.transform.scale_x) * preview_scale))
    height = max(1, round(pixel_height * abs(layer.transform.scale_y) * preview_scale))

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


def _open_rgba(content: bytes, owner: str) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            return source.convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise ProjectRenderError(f"{owner} contains unreadable image data.") from exc


def _transformed_bounds(
    *,
    width: float,
    height: float,
    transform: Transform,
    preview_scale: float,
) -> tuple[float, float, float, float]:
    scaled_width = width * abs(transform.scale_x) * preview_scale
    scaled_height = height * abs(transform.scale_y) * preview_scale
    angle = math.radians(transform.rotation_degrees)
    bounds_width = abs(scaled_width * math.cos(angle)) + abs(
        scaled_height * math.sin(angle)
    )
    bounds_height = abs(scaled_width * math.sin(angle)) + abs(
        scaled_height * math.cos(angle)
    )
    center_x = transform.x * preview_scale
    center_y = transform.y * preview_scale
    return (
        center_x - bounds_width / 2,
        center_y - bounds_height / 2,
        center_x + bounds_width / 2,
        center_y + bounds_height / 2,
    )


def _positive_property(layer: Layer, key: str) -> float:
    value = layer.properties.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ProjectRenderError(
            f"Layer {layer.name!r} must contain a positive numeric {key!r} property."
        )
    return float(value)
