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


@dataclass(frozen=True, slots=True)
class _PreparedAffineImage:
    image: Image.Image
    offset_x: float
    offset_y: float


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
            alpha = prepared.image.getchannel("A")
            inherited = effective_opacity / layer.opacity if layer.opacity else 0.0
            prepared.image.putalpha(ImageEnhance.Brightness(alpha).enhance(inherited))
        left = round(layer.transform.x * scale + prepared.offset_x)
        top = round(layer.transform.y * scale + prepared.offset_y)
        result.alpha_composite(prepared.image, dest=(left, top))

    return RenderedProject(image=result, scale=scale)


def object_shear(item: LayerObject) -> tuple[float, float]:
    """Return validated shear factors stored in backward-compatible object properties."""

    return _shear_values(item.properties)


def transformed_object_corners(
    item: LayerObject,
    *,
    preview_scale: float = 1.0,
) -> tuple[tuple[float, float], ...]:
    """Return clockwise transformed object corners in project or preview space."""

    shear_x, shear_y = object_shear(item)
    return _transformed_corners(
        width=item.bounds.width,
        height=item.bounds.height,
        transform=item.transform,
        shear_x=shear_x,
        shear_y=shear_y,
        preview_scale=preview_scale,
    )


def transform_object_local_point(
    item: LayerObject,
    local_x: float,
    local_y: float,
    *,
    preview_scale: float = 1.0,
) -> tuple[float, float]:
    """Map an object-local point to project or preview coordinates."""

    shear_x, shear_y = object_shear(item)
    a, b, c, d = _linear_matrix(
        item.transform,
        shear_x,
        shear_y,
        preview_scale=preview_scale,
    )
    return (
        item.transform.x * preview_scale + a * local_x + b * local_y,
        item.transform.y * preview_scale + c * local_x + d * local_y,
    )


def inverse_transform_object_point(
    item: LayerObject,
    x: float,
    y: float,
) -> tuple[float, float]:
    """Map one project-space point into the object's untransformed local coordinates."""

    shear_x, shear_y = object_shear(item)
    a, b, c, d = _linear_matrix(item.transform, shear_x, shear_y)
    determinant = a * d - b * c
    if abs(determinant) < 1e-10:
        raise ProjectRenderError("Object transform is singular.")
    inverse_a = d / determinant
    inverse_b = -b / determinant
    inverse_c = -c / determinant
    inverse_d = a / determinant
    delta_x = x - item.transform.x
    delta_y = y - item.transform.y
    return (
        inverse_a * delta_x + inverse_b * delta_y,
        inverse_c * delta_x + inverse_d * delta_y,
    )


def transformed_object_bounds(
    item: LayerObject,
    *,
    preview_scale: float = 1.0,
) -> tuple[float, float, float, float]:
    """Return an object's axis-aligned affine bounds around its center."""

    return _bounds_from_points(
        transformed_object_corners(item, preview_scale=preview_scale)
    )


def point_hits_object(item: LayerObject, x: float, y: float) -> bool:
    """Return whether a project-space point intersects the actual affine rectangle."""

    try:
        local_x, local_y = inverse_transform_object_point(item, x, y)
    except ProjectRenderError:
        return False
    return (
        -item.bounds.width / 2 <= local_x <= item.bounds.width / 2
        and -item.bounds.height / 2 <= local_y <= item.bounds.height / 2
    )


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
    shear_x, shear_y = _shear_values(layer.properties)
    return _bounds_from_points(
        _transformed_corners(
            width=width,
            height=height,
            transform=layer.transform,
            shear_x=shear_x,
            shear_y=shear_y,
            preview_scale=preview_scale,
        )
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
        left = round(item.transform.x * preview_scale + prepared.offset_x)
        top = round(item.transform.y * preview_scale + prepared.offset_y)
        if item.kind is ObjectKind.ERASER_STROKE:
            _erase_from_surface(surface, prepared.image, left, top)
        else:
            surface.alpha_composite(prepared.image, dest=(left, top))
    return surface


def _prepare_object_image(
    item: LayerObject,
    assets: Mapping[str, bytes],
    *,
    preview_scale: float,
) -> _PreparedAffineImage:
    source_width = max(1, round(item.bounds.width))
    source_height = max(1, round(item.bounds.height))
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
            image = render_shape_image(legacy_shape, source_width, source_height)
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
        image = image.resize((source_width, source_height), Image.Resampling.LANCZOS)

    shear_x, shear_y = object_shear(item)
    prepared = _apply_affine(
        image,
        item.transform,
        shear_x=shear_x,
        shear_y=shear_y,
        preview_scale=preview_scale,
    )
    if item.opacity < 1.0:
        alpha = prepared.image.getchannel("A")
        prepared.image.putalpha(ImageEnhance.Brightness(alpha).enhance(item.opacity))
    return prepared


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
) -> _PreparedAffineImage:
    pixel_width = _positive_property(layer, "pixel_width")
    pixel_height = _positive_property(layer, "pixel_height")
    source_width = max(1, round(pixel_width))
    source_height = max(1, round(pixel_height))

    if layer.kind is LayerKind.SHAPE:
        try:
            image = render_shape_image(layer, source_width, source_height)
        except ShapeError as exc:
            raise ProjectRenderError(
                f"Layer {layer.name!r} contains invalid shape data."
            ) from exc
    else:
        if content is None:
            raise MissingRasterAssetError(f"Layer {layer.name!r} has no raster content.")
        image = _open_rgba(content, f"Layer {layer.name!r}")
        image = image.resize((source_width, source_height), Image.Resampling.LANCZOS)

    shear_x, shear_y = _shear_values(layer.properties)
    prepared = _apply_affine(
        image,
        layer.transform,
        shear_x=shear_x,
        shear_y=shear_y,
        preview_scale=preview_scale,
    )
    if layer.opacity < 1.0:
        alpha = prepared.image.getchannel("A")
        prepared.image.putalpha(ImageEnhance.Brightness(alpha).enhance(layer.opacity))
    return prepared


def _apply_affine(
    image: Image.Image,
    transform: Transform,
    *,
    shear_x: float,
    shear_y: float,
    preview_scale: float,
) -> _PreparedAffineImage:
    a, b, c, d = _linear_matrix(
        transform,
        shear_x,
        shear_y,
        preview_scale=preview_scale,
    )
    determinant = a * d - b * c
    if abs(determinant) < 1e-10:
        raise ProjectRenderError("Transform is singular and cannot be rendered.")

    half_width = image.width / 2
    half_height = image.height / 2
    corners = (
        (a * -half_width + b * -half_height, c * -half_width + d * -half_height),
        (a * half_width + b * -half_height, c * half_width + d * -half_height),
        (a * half_width + b * half_height, c * half_width + d * half_height),
        (a * -half_width + b * half_height, c * -half_width + d * half_height),
    )
    min_x = math.floor(min(point[0] for point in corners))
    min_y = math.floor(min(point[1] for point in corners))
    max_x = math.ceil(max(point[0] for point in corners))
    max_y = math.ceil(max(point[1] for point in corners))
    output_width = max(1, max_x - min_x)
    output_height = max(1, max_y - min_y)

    inverse_a = d / determinant
    inverse_b = -b / determinant
    inverse_c = -c / determinant
    inverse_d = a / determinant
    coefficient_x = inverse_a * min_x + inverse_b * min_y + half_width
    coefficient_y = inverse_c * min_x + inverse_d * min_y + half_height
    transformed = image.transform(
        (output_width, output_height),
        Image.Transform.AFFINE,
        (
            inverse_a,
            inverse_b,
            coefficient_x,
            inverse_c,
            inverse_d,
            coefficient_y,
        ),
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )
    return _PreparedAffineImage(transformed, float(min_x), float(min_y))


def _linear_matrix(
    transform: Transform,
    shear_x: float,
    shear_y: float,
    *,
    preview_scale: float = 1.0,
) -> tuple[float, float, float, float]:
    scale_x = transform.scale_x * preview_scale
    scale_y = transform.scale_y * preview_scale
    unrotated_a = scale_x
    unrotated_b = shear_x * scale_y
    unrotated_c = shear_y * scale_x
    unrotated_d = scale_y
    angle = math.radians(transform.rotation_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return (
        cosine * unrotated_a - sine * unrotated_c,
        cosine * unrotated_b - sine * unrotated_d,
        sine * unrotated_a + cosine * unrotated_c,
        sine * unrotated_b + cosine * unrotated_d,
    )


def _transformed_corners(
    *,
    width: float,
    height: float,
    transform: Transform,
    shear_x: float,
    shear_y: float,
    preview_scale: float,
) -> tuple[tuple[float, float], ...]:
    a, b, c, d = _linear_matrix(
        transform,
        shear_x,
        shear_y,
        preview_scale=preview_scale,
    )
    center_x = transform.x * preview_scale
    center_y = transform.y * preview_scale
    half_width = width / 2
    half_height = height / 2
    return tuple(
        (center_x + a * x + b * y, center_y + c * x + d * y)
        for x, y in (
            (-half_width, -half_height),
            (half_width, -half_height),
            (half_width, half_height),
            (-half_width, half_height),
        )
    )


def _bounds_from_points(
    points: tuple[tuple[float, float], ...],
) -> tuple[float, float, float, float]:
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _shear_values(properties: Mapping[str, object]) -> tuple[float, float]:
    try:
        shear_x = float(properties.get("shear_x", 0.0))
        shear_y = float(properties.get("shear_y", 0.0))
    except (TypeError, ValueError) as exc:
        raise ProjectRenderError("Shear values must be numeric.") from exc
    if not math.isfinite(shear_x) or not math.isfinite(shear_y):
        raise ProjectRenderError("Shear values must be finite.")
    if abs(1.0 - shear_x * shear_y) < 1e-10:
        raise ProjectRenderError("Shear transform is singular.")
    return shear_x, shear_y


def _open_rgba(content: bytes, owner: str) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            return source.convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise ProjectRenderError(f"{owner} contains unreadable image data.") from exc


def _positive_property(layer: Layer, key: str) -> float:
    value = layer.properties.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ProjectRenderError(
            f"Layer {layer.name!r} must contain a positive numeric {key!r} property."
        )
    return float(value)
