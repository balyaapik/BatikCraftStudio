"""Shape-layer commands layered on top of the paint-enabled project session."""

from __future__ import annotations

from batikcraft_studio.domain import Layer, LayerKind, Transform
from batikcraft_studio.imaging.shape import (
    SHAPE_TYPES,
    ShapeError,
    build_shape_geometry,
    update_shape_properties,
)

from .paint_session import PaintProjectSession
from .session import ProjectSessionError


class ShapeLayerError(ProjectSessionError):
    """Raised when a shape command targets incompatible data."""


class ShapeProjectSession(PaintProjectSession):
    """Extend paint sessions with non-destructive line and shape layers."""

    def create_shape_layer(
        self,
        shape_type: str,
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        name: str | None = None,
        stroke_color: str = "#273043",
        fill_color: str = "#D9A566",
        stroke_width: float = 4.0,
        stroke_enabled: bool = True,
        fill_enabled: bool = True,
        polygon_sides: int = 6,
        constrain: bool = False,
        from_center: bool = False,
    ) -> Layer:
        """Create and select one editable shape layer from a pointer drag."""

        project = self.require_project()
        try:
            geometry = build_shape_geometry(
                shape_type,
                start,
                end,
                stroke_color=stroke_color,
                fill_color=fill_color,
                stroke_width=stroke_width,
                stroke_enabled=stroke_enabled,
                fill_enabled=fill_enabled,
                polygon_sides=polygon_sides,
                constrain=constrain,
                from_center=from_center,
            )
        except ShapeError as exc:
            raise ShapeLayerError(str(exc)) from exc

        shape_number = sum(
            layer.kind is LayerKind.SHAPE
            and layer.properties.get("shape_type") == shape_type
            for layer in project.layers
        ) + 1
        default_name = f"{shape_type.title()} {shape_number}"
        layer_name = (name or default_name).strip()
        if not layer_name:
            raise ShapeLayerError("Shape layer name must not be empty.")

        layer = Layer(
            name=layer_name[:120],
            kind=LayerKind.SHAPE,
            transform=Transform(x=geometry.center_x, y=geometry.center_y),
            properties=dict(geometry.properties),
        )
        self._commit_mutation(lambda: project.add_layer(layer))
        return layer

    def create_default_shape_layer(
        self,
        shape_type: str,
        *,
        stroke_color: str = "#273043",
        fill_color: str = "#D9A566",
        stroke_width: float = 4.0,
        stroke_enabled: bool = True,
        fill_enabled: bool = True,
        polygon_sides: int = 6,
    ) -> Layer:
        """Create a centered shape for the Layers context menu."""

        project = self.require_project()
        if shape_type not in SHAPE_TYPES:
            raise ShapeLayerError(f"Unsupported shape type: {shape_type!r}.")
        width = max(24.0, min(320.0, project.canvas.width * 0.28))
        height = max(24.0, min(220.0, project.canvas.height * 0.22))
        center = (project.canvas.width / 2, project.canvas.height / 2)
        start = (center[0] - width / 2, center[1] - height / 2)
        end = (center[0] + width / 2, center[1] + height / 2)
        return self.create_shape_layer(
            shape_type,
            start,
            end,
            stroke_color=stroke_color,
            fill_color=fill_color,
            stroke_width=stroke_width,
            stroke_enabled=stroke_enabled,
            fill_enabled=fill_enabled,
            polygon_sides=polygon_sides,
        )

    def update_shape_layer(
        self,
        layer_id: str,
        *,
        geometry_width: float | None = None,
        geometry_height: float | None = None,
        stroke_color: str | None = None,
        fill_color: str | None = None,
        stroke_width: float | None = None,
        stroke_enabled: bool | None = None,
        fill_enabled: bool | None = None,
        polygon_sides: int | None = None,
    ) -> Layer:
        """Update editable geometry and style while preserving layer transform."""

        project = self.require_project()
        layer = self._require_unlocked_layer(layer_id)
        if layer.kind is not LayerKind.SHAPE:
            raise ShapeLayerError("Shape properties require a shape layer.")
        try:
            properties = update_shape_properties(
                layer,
                geometry_width=geometry_width,
                geometry_height=geometry_height,
                stroke_color=stroke_color,
                fill_color=fill_color,
                stroke_width=stroke_width,
                stroke_enabled=stroke_enabled,
                fill_enabled=fill_enabled,
                polygon_sides=polygon_sides,
            )
        except ShapeError as exc:
            raise ShapeLayerError(str(exc)) from exc
        if properties == dict(layer.properties):
            return layer

        updated: Layer | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_layer(layer_id, properties=properties)

        self._commit_mutation(mutation)
        if updated is None:
            raise ShapeLayerError("Shape update did not produce a result.")
        return updated


__all__ = ["ShapeLayerError", "ShapeProjectSession"]
