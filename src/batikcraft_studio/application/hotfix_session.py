"""Critical session hotfixes for active-layer routing and enclosed fills."""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from uuid import uuid4

from PIL import ImageChops, Image, ImageColor, ImageDraw, ImageFilter, UnidentifiedImageError

from batikcraft_studio.domain import (
    Layer,
    LayerNodeKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Transform,
)
from batikcraft_studio.imaging.stroke_object import render_cropped_stroke

from .destructive_eraser_session import DestructiveEraserProjectSession
from .session import LayerLockedError, ProjectSessionError

_ALPHA_THRESHOLD = 28
_SUPERSAMPLE = 2
_GAP_CLOSE_PROJECT_PIXELS = 2


class HotfixProjectSession(DestructiveEraserProjectSession):
    """Desktop session with deterministic layer routing and reusable fill objects."""

    def ensure_active_paint_layer(self) -> Layer:
        """Use the selected editable layer instead of silently creating another layer."""

        project = self.require_project()
        active_id = project.active_layer_id
        if active_id is None:
            return self.create_paint_layer()

        active = project.get_layer(active_id)
        if project.is_layer_effectively_locked(active.layer_id):
            raise LayerLockedError(
                f"Layer {active.name!r} is locked and cannot receive new objects. "
                "Unlock it or select another layer."
            )
        if active.node_kind is LayerNodeKind.GROUP:
            return self.create_paint_layer(parent_id=active.layer_id)
        if active.asset_ref is not None:
            return self.create_paint_layer(parent_id=active.parent_id)
        if active.transform != Transform():
            raise ProjectSessionError(
                "The active layer container has a transform. Reset the layer transform "
                "or create a normal editable layer before drawing."
            )
        return active

    def apply_paint_stroke(
        self,
        layer_id: str,
        *,
        points: Sequence[tuple[float, float]],
        brush_size: float,
        color: str,
        erase: bool = False,
        opacity: float = 1.0,
        hardness: float = 1.0,
        smoothing: float = 0.0,
    ) -> Layer:
        """Insert a completed stroke into the explicitly selected editable layer."""

        project = self.require_project()
        layer = self._require_unlocked_layer(layer_id)
        if layer.node_kind is LayerNodeKind.GROUP:
            raise ProjectSessionError("Select an editable layer, not a layer folder.")
        if layer.asset_ref is not None:
            raise ProjectSessionError(
                "This legacy raster layer cannot contain editable objects. "
                "Select or create a normal layer."
            )
        if layer.transform != Transform():
            raise ProjectSessionError(
                "The active layer container must stay at the project origin. "
                "Transform the stroke object instead of the layer container."
            )

        cropped = render_cropped_stroke(
            canvas_width=project.canvas.width,
            canvas_height=project.canvas.height,
            points=list(points),
            brush_size=brush_size,
            color=color,
            opacity=opacity,
            hardness=hardness,
            smoothing=smoothing,
            eraser=erase,
        )
        asset_ref = f"assets/{uuid4()}.png"
        object_number = len(layer.objects) + 1
        item = LayerObject(
            name=("Hapus" if erase else "Gores Canting") + f" {object_number}",
            kind=ObjectKind.ERASER_STROKE if erase else ObjectKind.PAINT_STROKE,
            asset_ref=asset_ref,
            transform=Transform(x=cropped.center[0], y=cropped.center[1]),
            bounds=ObjectBounds(cropped.width, cropped.height),
            properties={
                "source_format": "ERASER_STROKE" if erase else "PAINT_STROKE",
                "brush_size": float(brush_size),
                "brush_color": color.upper(),
                "brush_opacity": float(opacity),
                "brush_hardness": float(hardness),
                "brush_smoothing": float(smoothing),
            },
        )

        def mutation() -> None:
            self._assets[asset_ref] = cropped.content
            project.add_object(layer.layer_id, item, select=True)
            refreshed = project.get_layer(layer.layer_id)
            properties = dict(refreshed.properties)
            properties["object_container"] = True
            properties["stroke_count"] = int(properties.get("stroke_count", 0)) + 1
            properties["last_tool"] = "eraser" if erase else "brush"
            properties["last_brush_size"] = float(brush_size)
            properties["last_brush_opacity"] = float(opacity)
            properties["last_brush_hardness"] = float(hardness)
            properties["last_brush_smoothing"] = float(smoothing)
            project.update_layer(layer.layer_id, properties=properties)

        self._commit_mutation(mutation)
        return project.get_layer(layer.layer_id)

    def fill_closed_object(self, object_id: str, color: str) -> tuple[LayerObject, ...]:
        """Fill a closed stroke completely and reuse its associated fill object."""

        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        if item.kind is ObjectKind.SHAPE:
            return super().fill_closed_object(object_id, color)
        if item.kind is not ObjectKind.PAINT_STROKE or item.asset_ref is None:
            raise ProjectSessionError(
                "Fill requires a closed vector shape or one closed paint stroke."
            )

        source_content = self._assets.get(item.asset_ref)
        if source_content is None:
            raise ProjectSessionError("The source stroke asset is unavailable.")
        normalized = _normalize_color(color)
        filled_content = _fill_enclosed_png_complete(source_content, normalized)

        layer_id = project.object_layer_id(item.object_id)
        layer = project.get_layer(layer_id)
        source_index = next(
            index for index, candidate in enumerate(layer.objects)
            if candidate.object_id == item.object_id
        )
        existing = next(
            (
                candidate
                for candidate in layer.objects
                if candidate.object_id != item.object_id
                and (
                    candidate.properties.get("source_stroke_id") == item.object_id
                    or candidate.properties.get("fill_source_object_id") == item.object_id
                )
            ),
            None,
        )
        new_asset_ref = f"assets/{uuid4()}.png"
        properties = {
            "source_format": "ENCLOSED_STROKE_FILL_V2",
            "fill_color": normalized,
            "source_stroke_id": item.object_id,
            "fill_source_object_id": item.object_id,
            "alpha_threshold": _ALPHA_THRESHOLD,
            "gap_close_project_pixels": _GAP_CLOSE_PROJECT_PIXELS,
            "supersample": _SUPERSAMPLE,
        }

        if existing is None:
            fill_object = LayerObject(
                name=f"Isi {item.name}"[:120],
                kind=ObjectKind.RASTER,
                asset_ref=new_asset_ref,
                transform=item.transform,
                bounds=item.bounds,
                properties=properties,
            )
            previous_asset_ref: str | None = None
        else:
            fill_object = existing
            previous_asset_ref = existing.asset_ref

        def mutation() -> None:
            self._assets[new_asset_ref] = filled_content
            if existing is None:
                project.add_object(
                    layer_id,
                    fill_object,
                    index=source_index,
                    select=False,
                )
            else:
                project.update_object(
                    existing.object_id,
                    asset_ref=new_asset_ref,
                    transform=item.transform,
                    bounds=item.bounds,
                    properties=properties,
                )
                # Keep the associated fill directly below its source stroke.
                project.move_object(existing.object_id, layer_id, index=source_index)
            if previous_asset_ref is not None:
                self._remove_asset_if_unreferenced(previous_asset_ref)

        self._commit_mutation(mutation)
        result_fill = project.get_object(fill_object.object_id)
        self.set_selected_objects([result_fill.object_id, item.object_id])
        return (result_fill, project.get_object(item.object_id))


def _normalize_color(value: str) -> str:
    try:
        rgb = ImageColor.getrgb(value)
    except (TypeError, ValueError) as exc:
        raise ProjectSessionError("Fill color must be a valid CSS color or #RRGGBB.") from exc
    return "#{:02X}{:02X}{:02X}".format(*rgb[:3])


def _fill_enclosed_png_complete(content: bytes, color: str) -> bytes:
    """Create a watertight, supersampled interior mask under the source stroke."""

    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            image = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProjectSessionError("The stroke cannot be decoded for Fill.") from exc

    width, height = image.size
    # Supersample memberi tepi mask lebih halus; untuk gambar besar biayanya
    # kuadratik, jadi gunakan 1x di atas ~0.6 MP (tepi 1 px tidak terlihat).
    scale = 1 if width * height >= 640_000 else _SUPERSAMPLE
    alpha = image.getchannel("A")
    if scale > 1:
        alpha = alpha.resize(
            (max(1, width * scale), max(1, height * scale)),
            Image.Resampling.LANCZOS,
        )
    barrier = alpha.point(lambda value: 255 if value >= _ALPHA_THRESHOLD else 0)

    # Expand just enough to close small accidental endpoint/sampling gaps.  The
    # threshold is in project pixels and therefore independent of viewport zoom.
    close_radius = _GAP_CLOSE_PROJECT_PIXELS * scale
    barrier = _iterated_morphology(barrier, close_radius, ImageFilter.MaxFilter)
    # Recover part of the original stroke thickness after closing the gap.
    erode_radius = max(1, scale - 1)
    barrier = _iterated_morphology(barrier, erode_radius, ImageFilter.MinFilter)

    free_space = barrier.point(lambda value: 0 if value else 255)
    interior = _interior_from_free_space(free_space)

    bbox = interior.getbbox()
    if bbox is None:
        raise ProjectSessionError(
            "The boundary is not closed enough to create a safe fill."
        )
    histogram = interior.histogram()
    interior_pixels = histogram[255]
    total_pixels = interior.width * interior.height
    if total_pixels <= 0 or interior_pixels / total_pixels > 0.90:
        raise ProjectSessionError(
            "The boundary is not closed enough to create a safe fill."
        )

    # One project-pixel underlap removes the transparent fringe beneath the line.
    interior = _iterated_morphology(interior, scale, ImageFilter.MaxFilter)
    if interior.size != (width, height):
        interior = interior.resize((width, height), Image.Resampling.LANCZOS)

    rgb = ImageColor.getrgb(color)[:3]
    filled = Image.new("RGBA", image.size, (*rgb, 0))
    filled.putalpha(interior)
    output = BytesIO()
    filled.save(output, format="PNG")
    return output.getvalue()


def _iterated_morphology(image: Image.Image, radius: int, factory: type) -> Image.Image:
    """Max/MinFilter(2r+1) sebagai r iterasi kernel 3x3 (jauh lebih cepat)."""
    for _ in range(max(0, radius)):
        image = image.filter(factory(3))
    return image


def _interior_from_free_space(free_space: Image.Image) -> Image.Image:
    """Return the enclosed-interior mask (255) of *free_space* (255 = passable).

    Scanline flood fill dari seluruh piksel tepi menandai eksterior; sisanya
    yang passable adalah interior. Jauh lebih cepat daripada
    ``ImageDraw.floodfill`` yang bekerja per piksel dengan set Python.
    """

    width, height = free_space.size
    src = free_space.tobytes()
    visited = bytearray(width * height)
    stack: list[tuple[int, int]] = []
    last_row = (height - 1) * width
    for x in range(width):
        if src[x]:
            stack.append((x, 0))
        if src[last_row + x]:
            stack.append((x, height - 1))
    for y in range(height):
        row = y * width
        if src[row]:
            stack.append((0, y))
        if src[row + width - 1]:
            stack.append((width - 1, y))

    while stack:
        x, y = stack.pop()
        row = y * width
        if visited[row + x] or not src[row + x]:
            continue
        x0 = x
        while x0 > 0 and src[row + x0 - 1] and not visited[row + x0 - 1]:
            x0 -= 1
        x1 = x
        while x1 < width - 1 and src[row + x1 + 1] and not visited[row + x1 + 1]:
            x1 += 1
        for cx in range(x0, x1 + 1):
            visited[row + cx] = 1
        for ny in (y - 1, y + 1):
            if 0 <= ny < height:
                nrow = ny * width
                cx = x0
                while cx <= x1:
                    if src[nrow + cx] and not visited[nrow + cx]:
                        stack.append((cx, ny))
                        cx += 1
                        while cx <= x1 and src[nrow + cx] and not visited[nrow + cx]:
                            cx += 1
                    else:
                        cx += 1

    exterior = Image.frombytes("L", (width, height), bytes(visited)).point(
        lambda value: 255 if value else 0
    )
    # interior = passable dan bukan eksterior
    return ImageChops.subtract(free_space, exterior)


def _fill_enclosed_png_unified(content: bytes, color: str) -> bytes:
    """Interior fill digabung DI BAWAH goresan asli menjadi satu gambar utuh.

    Dipakai oleh fill terpadu: hasilnya menggantikan asset objek goresan yang
    sama, bukan membuat objek "Isi" terpisah.
    """

    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            image = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProjectSessionError("The stroke cannot be decoded for Fill.") from exc

    filled_bytes = _fill_enclosed_png_complete(content, color)
    with Image.open(BytesIO(filled_bytes)) as fill_layer:
        fill_layer.load()
        combined = fill_layer.convert("RGBA")
    combined.alpha_composite(image)
    output = BytesIO()
    combined.save(output, format="PNG")
    return output.getvalue()


__all__ = ["HotfixProjectSession"]
