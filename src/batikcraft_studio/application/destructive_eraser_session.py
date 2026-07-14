"""Destructive pixel erasing for existing editable canvas objects."""

from __future__ import annotations

import math
from collections.abc import Sequence
from io import BytesIO
from uuid import uuid4

from PIL import Image, ImageChops, UnidentifiedImageError

from batikcraft_studio.domain import Layer, LayerKind, LayerObject, ObjectKind, Transform
from batikcraft_studio.imaging.affine_object import inverse_transform_point, object_linear_matrix
from batikcraft_studio.imaging.shape import ShapeError, render_shape_image
from batikcraft_studio.imaging.stroke_object import render_cropped_stroke

from .direct_style_session import DirectStyleProjectSession
from .session import ProjectSessionError

_ERASABLE_RASTER_KINDS = frozenset(
    {
        ObjectKind.RASTER,
        ObjectKind.PAINT_STROKE,
        ObjectKind.MOTIF,
        ObjectKind.ISEN,
    }
)


class DestructiveEraserProjectSession(DirectStyleProjectSession):
    """Erase pixels from the selected object instead of creating overlay eraser objects."""

    def erase_object_pixels(
        self,
        object_id: str,
        *,
        points: Sequence[tuple[float, float]],
        brush_size: float,
        opacity: float = 1.0,
        hardness: float = 1.0,
        smoothing: float = 0.0,
    ) -> LayerObject:
        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        if item.kind is not ObjectKind.SHAPE and item.kind not in _ERASABLE_RASTER_KINDS:
            raise ProjectSessionError(
                "Penghapus piksel hanya dapat dipakai pada shape, raster, motif, isen, "
                "atau goresan kuas."
            )
        if not points:
            raise ProjectSessionError("Goresan penghapus tidak memiliki titik.")

        source = _object_source_image(item, self._assets)
        local_points: list[tuple[float, float]] = []
        for world_x, world_y in points:
            local = inverse_transform_point(item, float(world_x), float(world_y))
            if local is None:
                raise ProjectSessionError("Transformasi objek tidak dapat dibalik untuk penghapus.")
            pixel_x = (local[0] / item.bounds.width + 0.5) * source.width
            pixel_y = (local[1] / item.bounds.height + 0.5) * source.height
            local_points.append((pixel_x, pixel_y))

        a, b, c, d = object_linear_matrix(item)
        world_scale = math.sqrt(max(abs(a * d - b * c), 1e-8))
        pixel_scale = math.sqrt(
            max(
                (source.width / item.bounds.width) * (source.height / item.bounds.height),
                1e-8,
            )
        )
        local_brush_size = max(0.25, float(brush_size) * pixel_scale / world_scale)
        stroke = render_cropped_stroke(
            canvas_width=source.width,
            canvas_height=source.height,
            points=local_points,
            brush_size=local_brush_size,
            color="#FFFFFF",
            opacity=opacity,
            hardness=hardness,
            smoothing=smoothing,
            eraser=False,
        )
        with Image.open(BytesIO(stroke.content)) as mask_source:
            mask_source.load()
            mask_crop = mask_source.convert("RGBA").getchannel("A")

        mask = Image.new("L", source.size, 0)
        left = round(stroke.center[0] - stroke.width / 2)
        top = round(stroke.center[1] - stroke.height / 2)
        mask.paste(mask_crop, (left, top))
        source.putalpha(ImageChops.subtract(source.getchannel("A"), mask))

        output = BytesIO()
        source.save(output, format="PNG", optimize=True)
        asset_ref = f"assets/{uuid4()}.png"
        previous_ref = item.asset_ref
        properties = dict(item.properties)
        properties.update(
            {
                "source_format": "PIXEL_ERASED_OBJECT",
                "eraser_editable": True,
                "eraser_last_brush_size": float(brush_size),
                "eraser_last_opacity": float(opacity),
                "eraser_last_hardness": float(hardness),
                "eraser_last_smoothing": float(smoothing),
            }
        )
        if item.kind is ObjectKind.SHAPE:
            properties["eraser_original_kind"] = ObjectKind.SHAPE.value
            properties["eraser_original_shape"] = dict(item.properties)

        def mutation() -> None:
            self._assets[asset_ref] = output.getvalue()
            project.update_object(
                item.object_id,
                kind=ObjectKind.RASTER if item.kind is ObjectKind.SHAPE else item.kind,
                asset_ref=asset_ref,
                properties=properties,
            )
            self._remove_asset_if_unreferenced(previous_ref)

        self._commit_mutation(mutation)
        self.set_selected_objects([item.object_id])
        return project.get_object(item.object_id)


def _object_source_image(item: LayerObject, assets: dict[str, bytes]) -> Image.Image:
    if item.kind is ObjectKind.SHAPE:
        width = max(1, round(item.bounds.width))
        height = max(1, round(item.bounds.height))
        legacy = Layer(
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
            return render_shape_image(legacy, width, height).convert("RGBA")
        except ShapeError as exc:
            raise ProjectSessionError("Shape tidak dapat dirasterisasi untuk penghapus.") from exc
    if item.asset_ref is None:
        raise ProjectSessionError("Objek tidak memiliki asset piksel yang dapat dihapus.")
    content = assets.get(item.asset_ref)
    if content is None:
        raise ProjectSessionError("Asset objek yang akan dihapus tidak tersedia.")
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            return source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProjectSessionError("Asset objek tidak dapat dibaca oleh penghapus.") from exc


__all__ = ["DestructiveEraserProjectSession"]
