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
from batikcraft_studio.imaging import live_bitmap_store
from batikcraft_studio.imaging.paint import PaintStrokeError
from batikcraft_studio.imaging.raster_stroke_layer import (
    blank_canvas_png,
    encode_canvas_png,
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
        # Layer full-canvas: renderer menempatkan bitmap berpusat di transform,
        # dan butuh pixel_width/pixel_height untuk tahu ukuran aslinya. Tanpa
        # ini render tile gagal diam-diam dan goresan tidak muncul.
        layer = Layer(
            name=layer_name or "Lapis Canting Raster",
            kind=LayerKind.PAINT,
            node_kind=LayerNodeKind.LAYER,
            parent_id=parent_id,
            asset_ref=asset_ref,
            transform=Transform(
                x=project.canvas.width / 2, y=project.canvas.height / 2
            ),
            properties={
                "source_format": "RASTER_CANVAS",
                "stroke_count": 0,
                "pixel_width": project.canvas.width,
                "pixel_height": project.canvas.height,
            },
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

        if not points:
            return layer  # goresan kosong

        # Ambil bitmap HIDUP (sudah didekode) dari store bersama; kalau tidak
        # ada, dekode sekali dari bytes.
        from io import BytesIO

        from PIL import Image

        from batikcraft_studio.imaging.paint import apply_stroke_to_image

        old_ref = layer.asset_ref
        base_image = live_bitmap_store.get(old_ref)
        if base_image is None:
            base_png = self._assets.get(old_ref)
            if base_png is None:
                base_image = Image.new(
                    "RGBA", (project.canvas.width, project.canvas.height), (0, 0, 0, 0)
                )
            else:
                with Image.open(BytesIO(base_png)) as decoded:
                    decoded.load()
                    base_image = decoded.convert("RGBA")
        # Gambar goresan LANGSUNG ke salinan bitmap hidup — tanpa
        # render_cropped_stroke yang mengalokasi + encode kanvas penuh
        # (~58 ms/goresan). Base disalin dulu agar state 'sebelum' untuk undo
        # tetap utuh. Hasil visual identik (memakai mask goresan yang sama).
        try:
            updated_image = apply_stroke_to_image(
                base_image.copy(),
                points=list(points),
                brush_size=brush_size,
                color=color,
                erase=erase,
                opacity=opacity,
                hardness=hardness,
                smoothing=smoothing,
            )
        except PaintStrokeError:
            return layer
        updated_png = encode_canvas_png(updated_image, fast=True)
        new_ref = f"assets/{uuid4()}.png"
        # Bagikan gambar hidup ke renderer supaya tidak perlu decode PNG lagi.
        live_bitmap_store.put(new_ref, updated_image)

        def mutation() -> None:
            self._assets[new_ref] = updated_png
            transform_changes: dict = {"asset_ref": new_ref}
            # Sembuhkan layer yang dibuat versi 0.9.7 tanpa transform pusat
            # (kalau ada) supaya bitmap-nya tampil.
            if layer.transform == Transform():
                transform_changes["transform"] = Transform(
                    x=project.canvas.width / 2, y=project.canvas.height / 2
                )
            project.update_layer(layer_id, **transform_changes)
            refreshed = project.get_layer(layer_id)
            properties = dict(refreshed.properties)
            properties["stroke_count"] = int(properties.get("stroke_count", 0)) + 1
            properties["last_tool"] = "eraser" if erase else "brush"
            properties["last_brush_size"] = float(brush_size)
            # Pastikan properti ukuran ada (renderer full-canvas memerlukannya).
            properties.setdefault("pixel_width", project.canvas.width)
            properties.setdefault("pixel_height", project.canvas.height)
            properties["source_format"] = "RASTER_CANVAS"
            project.update_layer(layer_id, properties=properties)
            # Aset lama tidak lagi dirujuk siapa pun; lepaskan agar arsip ramping.
            if old_ref and old_ref != new_ref:
                self._assets.pop(old_ref, None)

        self._commit_mutation(mutation)
        return project.get_layer(layer_id)


    def apply_raster_fill(
        self,
        layer_id: str,
        x: float,
        y: float,
        color: str,
        *,
        tolerance: int = 40,
    ) -> Layer:
        """Isi ember di titik (x, y) pada bitmap lapis canting raster.

        Klik di dalam area tertutup goresan -> terisi sampai batas. Satu mutasi
        undo. Memakai bitmap hidup (tanpa decode ulang) seperti jalur goresan.
        """

        project = self.require_project()
        layer = self._require_unlocked_layer(layer_id)
        if not self._is_raster_paint_layer(layer):
            raise PaintLayerError("Fill raster memerlukan lapis canting raster.")

        from io import BytesIO

        from PIL import Image

        from batikcraft_studio.imaging.raster_fill import flood_fill_image

        old_ref = layer.asset_ref
        base_image = live_bitmap_store.get(old_ref)
        if base_image is None:
            base_png = self._assets.get(old_ref)
            if base_png is None:
                base_image = Image.new(
                    "RGBA", (project.canvas.width, project.canvas.height), (0, 0, 0, 0)
                )
            else:
                with Image.open(BytesIO(base_png)) as decoded:
                    decoded.load()
                    base_image = decoded.convert("RGBA")

        filled = flood_fill_image(
            base_image, int(x), int(y), color, tolerance=tolerance
        )
        updated_png = encode_canvas_png(filled, fast=True)
        new_ref = f"assets/{uuid4()}.png"
        live_bitmap_store.put(new_ref, filled)

        def mutation() -> None:
            self._assets[new_ref] = updated_png
            transform_changes: dict = {"asset_ref": new_ref}
            if layer.transform == Transform():
                transform_changes["transform"] = Transform(
                    x=project.canvas.width / 2, y=project.canvas.height / 2
                )
            project.update_layer(layer_id, **transform_changes)
            refreshed = project.get_layer(layer_id)
            properties = dict(refreshed.properties)
            properties.setdefault("pixel_width", project.canvas.width)
            properties.setdefault("pixel_height", project.canvas.height)
            properties["source_format"] = "RASTER_CANVAS"
            project.update_layer(layer_id, properties=properties)
            if old_ref and old_ref != new_ref:
                self._assets.pop(old_ref, None)

        self._commit_mutation(mutation)
        return project.get_layer(layer_id)


__all__ = [
    "LayerLockedError",
    "PaintLayerError",
    "PaintProjectSession",
]
