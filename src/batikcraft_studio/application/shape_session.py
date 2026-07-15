"""Shape-layer commands layered on top of the paint-enabled project session."""

from __future__ import annotations

from batikcraft_studio.domain import Layer, LayerKind, LayerNodeKind, Transform
from batikcraft_studio.imaging.shape import (
    SHAPE_TYPES,
    ShapeError,
    build_shape_geometry,
    update_shape_properties,
)

from .paint_session import PaintProjectSession
from .session import LayerLockedError, ProjectSessionError


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

    def _resolve_object_layer(self, layer_id: str | None, *, name: str) -> tuple[Layer, bool]:
        """Resolve an object-insertion target, respecting the active layer selection.

        This base implementation is overridden by ``CanvasStructureProjectSession``
        and ``ObjectProjectSession`` in the full application stack.  It provides a
        minimal, correct implementation so that ``BatikProjectSession`` and
        ``MotifProjectSession`` work correctly when used directly (e.g. in tests).

        Returns a ``(layer, needs_add)`` pair.  When *needs_add* is ``True`` the
        caller is responsible for calling ``project.add_layer(layer)`` inside the
        same ``_commit_mutation`` block so that layer creation and object insertion
        share one undo/redo history entry.

        Resolution order
        ----------------
        1. Explicit *layer_id* → validate and use directly.
        2. Active layer that is a valid unlocked object layer → use it.
        3. Active layer that is locked → raise ``LayerLockedError``.
        4. No suitable active layer → return a new ``Layer`` with ``needs_add=True``.
        """

        project = self.require_project()

        if layer_id is not None:
            candidate = project.get_layer(layer_id)
            if candidate.node_kind is not LayerNodeKind.LAYER or candidate.asset_ref is not None:
                raise LayerLockedError(
                    "The selected target is not a valid object layer."
                )
            if project.is_layer_effectively_locked(candidate.layer_id):
                raise LayerLockedError(
                    f"Layer {candidate.name!r} is locked and cannot receive new objects."
                )
            return candidate, False

        active_id = project.active_layer_id
        if active_id is not None:
            active = project.get_layer(active_id)
            if (
                active.node_kind is LayerNodeKind.LAYER
                and active.asset_ref is None
            ):
                if project.is_layer_effectively_locked(active.layer_id):
                    raise LayerLockedError(
                        f"Layer {active.name!r} is locked and cannot receive new objects. "
                        "Unlock the layer or select a different layer."
                    )
                return active, False

        # Fallback: return a new layer that the caller must add inside its mutation.
        new_layer = Layer(
            name=name,
            kind=LayerKind.BATIKIFIED_OBJECT,
            node_kind=LayerNodeKind.LAYER,
            properties={"object_container": True},
        )
        return new_layer, True


__all__ = ["ShapeLayerError", "ShapeProjectSession"]
