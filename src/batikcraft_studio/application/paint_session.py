"""Paint-object commands layered on top of the stable project session."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Transform,
)
from batikcraft_studio.imaging.raster_stroke_layer import (
    blank_canvas_png,
    composite_stroke_onto_canvas,
)
from batikcraft_studio.imaging.stroke_object import render_cropped_stroke

from .session import LayerLockedError, ProjectSession, ProjectSessionError


class PaintLayerError(ProjectSessionError):
    """Raised when a paint command targets an incompatible layer."""


class PaintProjectSession(ProjectSession):
    """Extend project sessions with multi-object paint-layer operations."""

    def create_paint_layer(
        self,
        name: str | None = None,
        *,
        parent_id: str | None = None,
    ) -> Layer:
        """Create a paint container; completed strokes become child objects."""

        project = self.require_project()
        paint_number = sum(layer.kind is LayerKind.PAINT for layer in project.layers) + 1
        layer_name = (name or f"Lapis Canting {paint_number}").strip()
        if not layer_name:
            raise PaintLayerError("Nama lapis canting tidak boleh kosong.")

        layer = Layer(
            name=layer_name[:120],
            kind=LayerKind.PAINT,
            node_kind=LayerNodeKind.LAYER,
            parent_id=parent_id,
            properties={
                "object_container": True,
                "source_format": "PAINT_OBJECTS",
                "stroke_count": 0,
            },
        )
        self._commit_mutation(lambda: project.add_layer(layer))
        return layer

    def ensure_active_paint_layer(self) -> Layer:
        """Return the active editable paint container, or create a new one.

        Rules
        -----
        * If the active layer is a valid paint container, return it.
        * If the active layer is a locked paint container, raise LayerLockedError.
        * If the active layer is any other type (shape, raster, batikified…), create
          a new paint layer *without* silently ignoring the selected layer.
        * If no layer is selected, create a new paint layer.
        """

        project = self.require_project()
        if project.active_layer_id is not None:
            active = project.get_layer(project.active_layer_id)
            if (
                active.kind is LayerKind.PAINT
                and active.node_kind is LayerNodeKind.LAYER
                and active.asset_ref is None
                and active.transform == Transform()
            ):
                if project.is_layer_effectively_locked(active.layer_id):
                    raise LayerLockedError(
                        f"Layer {active.name!r} is locked and cannot receive new objects. "
                        "Unlock the layer or select a different layer."
                    )
                return active
        return self.create_paint_layer()

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
        """Commit one tightly bounded stroke object as one undoable mutation."""

        project = self.require_project()
        layer = self._require_unlocked_layer(layer_id)
        if layer.kind is not LayerKind.PAINT or layer.node_kind is LayerNodeKind.GROUP:
            raise PaintLayerError("Kuas dan penghapus memerlukan lapis canting.")
        if layer.asset_ref is not None:
            raise PaintLayerError(
                "Lapis cat lama berbasis kanvas penuh tidak dipakai untuk stroke baru; "
                "buat Lapis Canting baru."
            )
        if layer.transform != Transform():
            raise PaintLayerError(
                "Lapis canting container harus tetap di posisi asal, tanpa rotasi atau skala; "
                "transformasikan objek goresannya."
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
            project.add_object(layer_id, item, select=True)
            refreshed = project.get_layer(layer_id)
            properties = dict(refreshed.properties)
            properties["stroke_count"] = int(properties.get("stroke_count", 0)) + 1
            properties["last_tool"] = "eraser" if erase else "brush"
            properties["last_brush_size"] = float(brush_size)
            properties["last_brush_opacity"] = float(opacity)
            properties["last_brush_hardness"] = float(hardness)
            properties["last_brush_smoothing"] = float(smoothing)
            project.update_layer(layer_id, properties=properties)

        self._commit_mutation(mutation)
        return project.get_layer(layer_id)


    # ------------------------------------------------------------------
    # Lapis canting RASTER: goresan melebur ke satu bitmap (bukan objek per
    # goresan). Menjaga menggambar tetap ringan berapa pun banyak goresannya,
    # sambil tetap disimpan di .batikcraft sebagai satu PNG per layer.
    # ------------------------------------------------------------------

    def create_raster_paint_layer(
        self, name: str | None = None, *, parent_id: str | None = None
    ) -> Layer:
        """Buat lapis canting raster: satu bitmap kanvas penuh untuk digambari."""

        project = self.require_project()
        number = sum(layer.kind is LayerKind.PAINT for layer in project.layers) + 1
        layer_name = (name or f"Lapis Canting Raster {number}").strip()[:120]
        asset_ref = f"assets/{uuid4()}.png"
        blank = blank_canvas_png(project.canvas.width, project.canvas.height)
        layer = Layer(
            name=layer_name or "Lapis Canting Raster",
            kind=LayerKind.PAINT,
            node_kind=LayerNodeKind.LAYER,
            parent_id=parent_id,
            asset_ref=asset_ref,
            properties={"source_format": "RASTER_CANVAS", "stroke_count": 0},
        )

        def mutation() -> None:
            self._assets[asset_ref] = blank
            project.add_layer(layer)

        self._commit_mutation(mutation)
        return project.get_layer(layer.layer_id)

    def _is_raster_paint_layer(self, layer: Layer) -> bool:
        return (
            layer.kind is LayerKind.PAINT
            and layer.node_kind is LayerNodeKind.LAYER
            and layer.asset_ref is not None
            and str(layer.properties.get("source_format")) == "RASTER_CANVAS"
        )

    def ensure_active_raster_paint_layer(self) -> Layer:
        """Kembalikan lapis canting raster aktif, atau buat baru bila belum ada."""

        project = self.require_project()
        if project.active_layer_id is not None:
            active = project.get_layer(project.active_layer_id)
            if self._is_raster_paint_layer(active):
                if project.is_layer_effectively_locked(active.layer_id):
                    raise LayerLockedError(
                        f"Layer {active.name!r} terkunci. Buka kunci atau pilih layer lain."
                    )
                return active
        return self.create_raster_paint_layer()

    def apply_raster_paint_stroke(
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
        """Leburkan satu goresan ke bitmap lapis canting raster (satu mutasi)."""

        project = self.require_project()
        layer = self._require_unlocked_layer(layer_id)
        if not self._is_raster_paint_layer(layer):
            raise PaintLayerError("Goresan raster memerlukan lapis canting raster.")

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
        if cropped.width <= 0 or cropped.height <= 0:
            return layer  # goresan kosong

        base_png = self._assets.get(layer.asset_ref)
        if base_png is None:
            base_png = blank_canvas_png(project.canvas.width, project.canvas.height)
        updated_png = composite_stroke_onto_canvas(
            base_png, cropped.content, cropped.left, cropped.top, erase=erase
        )
        new_ref = f"assets/{uuid4()}.png"
        old_ref = layer.asset_ref

        def mutation() -> None:
            self._assets[new_ref] = updated_png
            project.update_layer(layer_id, asset_ref=new_ref)
            refreshed = project.get_layer(layer_id)
            properties = dict(refreshed.properties)
            properties["stroke_count"] = int(properties.get("stroke_count", 0)) + 1
            properties["last_tool"] = "eraser" if erase else "brush"
            properties["last_brush_size"] = float(brush_size)
            project.update_layer(layer_id, properties=properties)
            # Aset lama tidak lagi dirujuk siapa pun; lepaskan agar arsip ramping.
            if old_ref and old_ref != new_ref:
                self._assets.pop(old_ref, None)

        self._commit_mutation(mutation)
        return project.get_layer(layer_id)


__all__ = [
    "LayerLockedError",
    "PaintLayerError",
    "PaintProjectSession",
]
