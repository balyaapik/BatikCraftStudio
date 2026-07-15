"""Object-first layer containers, folder-aware shape creation, and fill commands."""

from __future__ import annotations

from pathlib import Path

from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    ObjectNotFoundError,
    Transform,
)
from batikcraft_studio.imaging.shape import (
    SHAPE_TYPES,
    ShapeError,
    build_shape_geometry,
    update_shape_properties,
)

from .process_session import BatikProcessProjectSession
from .session import LayerLockedError, ProjectSessionError
from .shape_session import ShapeLayerError

_CLOSED_SHAPES = frozenset({"rectangle", "ellipse", "polygon"})
_INTERNAL_HIDDEN_KEY = "internal_hidden"


class CanvasStructureProjectSession(BatikProcessProjectSession):
    """Make layers true multi-object containers and folders true layer containers."""

    def __init__(self, model_root: Path | str | None = None) -> None:
        super().__init__(model_root)

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
        target_layer_id: str | None = None,
    ) -> LayerObject:
        """Create a shape object inside an existing layer instead of creating a layer."""

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

        target, add_target = self._resolve_object_layer(target_layer_id, name="Layer Bentuk")
        shape_number = (
            sum(
                item.kind is ObjectKind.SHAPE
                and item.properties.get("shape_type") == shape_type
                for layer in project.layers
                for item in layer.objects
            )
            + 1
        )
        default_name = f"{shape_type.title()} {shape_number}"
        object_name = (name or default_name).strip()
        if not object_name:
            raise ShapeLayerError("Nama objek bentuk tidak boleh kosong.")
        properties = dict(geometry.properties)
        properties.update(
            {
                "source_format": "VECTOR_SHAPE_OBJECT",
                "closed_shape": shape_type in _CLOSED_SHAPES,
            }
        )
        item = LayerObject(
            name=object_name[:120],
            kind=ObjectKind.SHAPE,
            transform=Transform(x=geometry.center_x, y=geometry.center_y),
            bounds=ObjectBounds(
                float(properties["pixel_width"]),
                float(properties["pixel_height"]),
            ),
            properties=properties,
        )

        def _shape_mutation() -> None:
            if add_target:
                project.add_layer(target)
            project.add_object(target.layer_id, item, select=True)

        self._commit_mutation(_shape_mutation)
        return item

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
        target_layer_id: str | None = None,
    ) -> LayerObject:
        """Create a centered shape object in the selected layer or folder."""

        project = self.require_project()
        if shape_type not in SHAPE_TYPES:
            raise ShapeLayerError(f"Unsupported shape type: {shape_type!r}.")
        width = max(24.0, min(320.0, project.canvas.width * 0.28))
        height = max(24.0, min(220.0, project.canvas.height * 0.22))
        center = (project.canvas.width / 2, project.canvas.height / 2)
        return self.create_shape_layer(
            shape_type,
            (center[0] - width / 2, center[1] - height / 2),
            (center[0] + width / 2, center[1] + height / 2),
            stroke_color=stroke_color,
            fill_color=fill_color,
            stroke_width=stroke_width,
            stroke_enabled=stroke_enabled,
            fill_enabled=fill_enabled,
            polygon_sides=polygon_sides,
            target_layer_id=target_layer_id,
        )

    def update_shape_layer(
        self,
        target_id: str,
        *,
        geometry_width: float | None = None,
        geometry_height: float | None = None,
        stroke_color: str | None = None,
        fill_color: str | None = None,
        stroke_width: float | None = None,
        stroke_enabled: bool | None = None,
        fill_enabled: bool | None = None,
        polygon_sides: int | None = None,
    ) -> LayerObject | Layer:
        """Update a shape object, while retaining support for legacy shape layers."""

        project = self.require_project()
        try:
            item = project.get_object(target_id)
        except ObjectNotFoundError:
            return super().update_shape_layer(
                target_id,
                geometry_width=geometry_width,
                geometry_height=geometry_height,
                stroke_color=stroke_color,
                fill_color=fill_color,
                stroke_width=stroke_width,
                stroke_enabled=stroke_enabled,
                fill_enabled=fill_enabled,
                polygon_sides=polygon_sides,
            )
        if item.kind is not ObjectKind.SHAPE:
            raise ShapeLayerError("Properti bentuk hanya berlaku untuk objek shape.")
        self._require_unlocked_object(item.object_id)
        properties = self._updated_shape_object_properties(
            item,
            geometry_width=geometry_width,
            geometry_height=geometry_height,
            stroke_color=stroke_color,
            fill_color=fill_color,
            stroke_width=stroke_width,
            stroke_enabled=stroke_enabled,
            fill_enabled=fill_enabled,
            polygon_sides=polygon_sides,
        )
        updated: LayerObject | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_object(
                item.object_id,
                bounds=ObjectBounds(
                    float(properties["pixel_width"]),
                    float(properties["pixel_height"]),
                ),
                properties=properties,
            )

        self._commit_mutation(mutation)
        if updated is None:
            raise ShapeLayerError("Perubahan objek shape tidak menghasilkan hasil.")
        return updated

    def set_selected_closed_shape_fill(self, color: str) -> tuple[LayerObject, ...]:
        """Apply one fill color to all selected closed shape objects as one Undo step."""

        project = self.require_project()
        targets = tuple(item for item in self.selected_objects if self.is_closed_shape(item))
        if not targets:
            raise ProjectSessionError(
                "Pilih rectangle, ellipse, atau polygon sebelum memberi fill color."
            )
        replacements: dict[str, tuple[dict[str, object], ObjectBounds]] = {}
        for item in targets:
            self._require_unlocked_object(item.object_id)
            properties = self._updated_shape_object_properties(
                item,
                fill_color=color,
                fill_enabled=True,
            )
            replacements[item.object_id] = (
                properties,
                ObjectBounds(
                    float(properties["pixel_width"]),
                    float(properties["pixel_height"]),
                ),
            )

        def mutation() -> None:
            for object_id, (properties, bounds) in replacements.items():
                project.update_object(object_id, properties=properties, bounds=bounds)

        self._commit_mutation(mutation)
        self.set_selected_objects([item.object_id for item in targets])
        return tuple(project.get_object(item.object_id) for item in targets)

    def move_selected_objects_to_layer(self, layer_id: str) -> tuple[LayerObject, ...]:
        """Move the current multi-selection into one layer container as one Undo step."""

        project = self.require_project()
        target = project.get_layer(layer_id)
        if not self._is_object_container(target):
            raise ProjectSessionError("Tujuan harus berupa layer objek, bukan folder.")
        if project.is_layer_effectively_locked(target.layer_id):
            raise LayerLockedError(f"Layer {target.name!r} sedang dikunci.")
        selected = self.selected_objects
        if not selected:
            raise ProjectSessionError("Tidak ada objek yang dipilih.")
        for item in selected:
            self._require_unlocked_object(item.object_id)

        def mutation() -> None:
            for item in selected:
                if project.object_layer_id(item.object_id) != target.layer_id:
                    project.move_object(item.object_id, target.layer_id)

        self._commit_mutation(mutation)
        self.set_selected_objects([item.object_id for item in selected])
        return tuple(project.get_object(item.object_id) for item in selected)

    def create_layer_for_current_context(self, name: str = "Layer Objek") -> Layer:
        """Create a layer inside the selected folder, or beside the selected layer."""

        project = self.require_project()
        parent_id: str | None = None
        active_id = project.active_layer_id
        if active_id is not None:
            active = project.get_layer(active_id)
            if active.node_kind is LayerNodeKind.GROUP and not active.properties.get(
                _INTERNAL_HIDDEN_KEY
            ):
                parent_id = active.layer_id
            else:
                parent_id = active.parent_id
        return self.create_object_layer(name=name, parent_id=parent_id)

    def create_folder_for_current_context(self, name: str = "Folder Layer") -> Layer:
        """Create a folder inside the selected folder, or beside the selected layer."""

        project = self.require_project()
        parent_id: str | None = None
        active_id = project.active_layer_id
        if active_id is not None:
            active = project.get_layer(active_id)
            if active.node_kind is LayerNodeKind.GROUP and not active.properties.get(
                _INTERNAL_HIDDEN_KEY
            ):
                parent_id = active.layer_id
            else:
                parent_id = active.parent_id
        return self.create_folder(name=name, parent_id=parent_id)

    @property
    def object_layers(self) -> tuple[Layer, ...]:
        """Return visible user-facing layers that may contain many objects."""

        project = self.project
        if project is None:
            return ()
        return tuple(layer for layer in project.layers if self._is_object_container(layer))

    @staticmethod
    def is_closed_shape(item: LayerObject) -> bool:
        return (
            item.kind is ObjectKind.SHAPE
            and item.properties.get("shape_type") in _CLOSED_SHAPES
        )

    def _resolve_object_layer(self, layer_id: str | None, *, name: str) -> tuple[Layer, bool]:
        """Resolve an object-insertion target, respecting the active layer selection.

        Returns a ``(layer, needs_add)`` pair.  When *needs_add* is ``True`` the
        caller must call ``project.add_layer(layer)`` inside the same
        ``_commit_mutation`` block so that layer creation and object insertion
        share exactly one undo/redo entry.

        Resolution order
        ----------------
        1. If *layer_id* is supplied explicitly, validate and use it directly.
        2. If the active layer is a valid, unlocked object container, use it.
        3. If the active layer is a locked object container → raise LayerLockedError.
        4. If no active layer is set, or the active node is a folder, create a new
           layer in the right position (folder child or root).

        This ensures that the user's current selection is always honoured and that
        locked layers never silently redirect objects to a different layer.
        """

        project = self.require_project()

        # ---- Explicit caller-supplied target ----
        if layer_id is not None:
            target = project.get_layer(layer_id)
            if target.node_kind is LayerNodeKind.GROUP:
                raise LayerLockedError(
                    "Objects cannot be inserted directly into a folder. "
                    "Select or create an editable layer inside the folder first."
                )
            if project.is_layer_effectively_locked(target.layer_id):
                raise LayerLockedError(
                    f"Layer {target.name!r} is locked and cannot receive new objects. "
                    "Unlock the layer first."
                )
            return target, False

        # ---- Active layer (user's current tree selection) ----
        active_id = project.active_layer_id
        if active_id is not None:
            active = project.get_layer(active_id)

            if active.node_kind is LayerNodeKind.GROUP and not active.properties.get(
                _INTERNAL_HIDDEN_KEY
            ):
                # Folder selected → create inside it without silently redirecting.
                return self.create_object_layer(name, parent_id=active.layer_id), False

            if self._is_object_container(active):
                if project.is_layer_effectively_locked(active.layer_id):
                    raise LayerLockedError(
                        f"Layer {active.name!r} is locked and cannot receive new objects. "
                        "Unlock the layer or select a different layer."
                    )
                # Valid, unlocked object layer → use it directly.
                return active, False

            # Some other non-container layer type (e.g. legacy raster layer) →
            # create beside it inside the same folder.
            return self.create_object_layer(name, parent_id=active.parent_id), False

        # ---- No active layer at all ----
        return self.create_object_layer(name), False

    @staticmethod
    def _is_object_container(layer: Layer) -> bool:
        return (
            layer.node_kind is LayerNodeKind.LAYER
            and layer.asset_ref is None
            and not layer.properties.get(_INTERNAL_HIDDEN_KEY)
        )

    @staticmethod
    def _shape_object_as_legacy_layer(item: LayerObject) -> Layer:
        return Layer(
            name=item.name,
            kind=LayerKind.SHAPE,
            transform=Transform(),
            properties={
                **dict(item.properties),
                "pixel_width": item.bounds.width,
                "pixel_height": item.bounds.height,
            },
        )

    def _updated_shape_object_properties(
        self,
        item: LayerObject,
        **changes: object,
    ) -> dict[str, object]:
        legacy = self._shape_object_as_legacy_layer(item)
        try:
            properties = update_shape_properties(legacy, **changes)
        except ShapeError as exc:
            raise ShapeLayerError(str(exc)) from exc
        properties["source_format"] = "VECTOR_SHAPE_OBJECT"
        properties["closed_shape"] = properties.get("shape_type") in _CLOSED_SHAPES
        return properties


__all__ = ["CanvasStructureProjectSession"]
