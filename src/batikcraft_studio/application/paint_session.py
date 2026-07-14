"""Paint-layer commands layered on top of the stable project session."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from batikcraft_studio.domain import Layer, LayerKind, Transform
from batikcraft_studio.imaging.paint import apply_paint_stroke, create_transparent_canvas_png

from .session import LayerLockedError, ProjectSession, ProjectSessionError


class PaintLayerError(ProjectSessionError):
    """Raised when a paint command targets an incompatible layer."""


class PaintProjectSession(ProjectSession):
    """Extend project sessions with full-canvas paint-layer operations."""

    def create_paint_layer(self, name: str | None = None) -> Layer:
        """Create and select a transparent paint layer aligned to the project canvas."""

        project = self.require_project()
        paint_number = sum(layer.kind is LayerKind.PAINT for layer in project.layers) + 1
        layer_name = (name or f"Paint Layer {paint_number}").strip()
        if not layer_name:
            raise PaintLayerError("Paint layer name must not be empty.")

        asset_ref = f"assets/{uuid4()}.png"
        content = create_transparent_canvas_png(project.canvas.width, project.canvas.height)
        layer = Layer(
            name=layer_name[:120],
            kind=LayerKind.PAINT,
            asset_ref=asset_ref,
            transform=Transform(
                x=project.canvas.width / 2,
                y=project.canvas.height / 2,
            ),
            properties={
                "pixel_width": project.canvas.width,
                "pixel_height": project.canvas.height,
                "source_format": "PAINT",
                "canvas_aligned": True,
                "stroke_count": 0,
            },
        )

        def mutation() -> None:
            self._assets[asset_ref] = content
            project.add_layer(layer)

        self._commit_mutation(mutation)
        return layer

    def ensure_active_paint_layer(self) -> Layer:
        """Return the active editable paint layer or create a new one."""

        project = self.require_project()
        if project.active_layer_id is not None:
            active = project.get_layer(project.active_layer_id)
            if (
                active.kind is LayerKind.PAINT
                and not active.locked
                and _is_canvas_aligned(active, project.canvas.width, project.canvas.height)
            ):
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
        """Commit one complete refined stroke as one undoable mutation."""

        project = self.require_project()
        layer = self._require_unlocked_layer(layer_id)
        if layer.kind is not LayerKind.PAINT:
            raise PaintLayerError("Brush and eraser tools require a paint layer.")
        if layer.asset_ref is None:
            raise PaintLayerError("Paint layer does not reference an image asset.")
        if not _is_canvas_aligned(layer, project.canvas.width, project.canvas.height):
            raise PaintLayerError(
                "Paint layer must remain centered, unrotated, and unscaled while drawing."
            )
        try:
            current_content = self._assets[layer.asset_ref]
        except KeyError as exc:
            raise PaintLayerError("Paint layer image asset is missing.") from exc

        updated_content = apply_paint_stroke(
            current_content,
            width=project.canvas.width,
            height=project.canvas.height,
            points=points,
            brush_size=brush_size,
            color=color,
            erase=erase,
            opacity=opacity,
            hardness=hardness,
            smoothing=smoothing,
        )
        if updated_content == current_content:
            return layer

        updated_layer: Layer | None = None

        def mutation() -> None:
            nonlocal updated_layer
            properties = dict(layer.properties)
            properties["stroke_count"] = int(properties.get("stroke_count", 0)) + 1
            properties["last_tool"] = "eraser" if erase else "brush"
            properties["last_brush_size"] = float(brush_size)
            properties["last_brush_opacity"] = float(opacity)
            properties["last_brush_hardness"] = float(hardness)
            properties["last_brush_smoothing"] = float(smoothing)
            self._assets[layer.asset_ref] = updated_content
            updated_layer = project.update_layer(layer_id, properties=properties)

        self._commit_mutation(mutation)
        if updated_layer is None:
            raise PaintLayerError("Paint stroke did not produce an updated layer.")
        return updated_layer


def _is_canvas_aligned(layer: Layer, width: int, height: int) -> bool:
    transform = layer.transform
    return (
        transform.x == width / 2
        and transform.y == height / 2
        and transform.rotation_degrees == 0
        and transform.scale_x == 1
        and transform.scale_y == 1
        and layer.properties.get("pixel_width") == width
        and layer.properties.get("pixel_height") == height
    )


__all__ = [
    "LayerLockedError",
    "PaintLayerError",
    "PaintProjectSession",
]
