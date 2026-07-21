"""Project aggregate for editable BatikCraft motif documents."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from batikcraft_studio.domain.errors import (
    DuplicateLayerError,
    DuplicateObjectError,
    LayerNotFoundError,
    ObjectNotFoundError,
    ProjectValidationError,
)
from batikcraft_studio.domain.models import (
    CURRENT_SCHEMA_VERSION,
    CanvasSpec,
    Layer,
    LayerNodeKind,
    LayerObject,
    ProjectMetadata,
)


class Project:
    """Aggregate root that owns metadata, canvas, layer tree, and objects."""

    __slots__ = (
        "_active_layer_id",
        "_active_object_id",
        "_canvas",
        "_created_at",
        "_layers",
        "_metadata",
        "_project_id",
        "_revision",
        "_saved_revision",
        "_schema_version",
        "_updated_at",
    )

    def __init__(
        self,
        *,
        metadata: ProjectMetadata,
        canvas: CanvasSpec | None = None,
        layers: tuple[Layer, ...] | list[Layer] = (),
        project_id: str | None = None,
        schema_version: str = CURRENT_SCHEMA_VERSION,
        active_layer_id: str | None = None,
        active_object_id: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        revision: int = 0,
        saved_revision: int = -1,
    ) -> None:
        now = datetime.now(UTC)
        self._project_id = project_id or str(uuid4())
        self._schema_version = schema_version
        self._metadata = metadata
        self._canvas = canvas or CanvasSpec()
        self._layers = list(layers)
        self._active_layer_id = active_layer_id
        self._active_object_id = active_object_id
        self._created_at = created_at or now
        self._updated_at = updated_at or self._created_at
        self._revision = revision
        self._saved_revision = saved_revision
        self.assert_valid()

    @classmethod
    def create(
        cls,
        title: str,
        creator: str,
        *,
        description: str = "",
        tags: tuple[str, ...] = (),
        canvas: CanvasSpec | None = None,
    ) -> Project:
        """Create a new, unsaved motif project."""

        return cls(
            metadata=ProjectMetadata(
                title=title,
                creator=creator,
                description=description,
                tags=tags,
            ),
            canvas=canvas,
        )

    @property
    def project_id(self) -> str:
        return self._project_id

    @property
    def schema_version(self) -> str:
        return self._schema_version

    @property
    def metadata(self) -> ProjectMetadata:
        return self._metadata

    @property
    def canvas(self) -> CanvasSpec:
        return self._canvas

    @property
    def layers(self) -> tuple[Layer, ...]:
        return tuple(self._layers)

    @property
    def active_layer_id(self) -> str | None:
        return self._active_layer_id

    @property
    def active_object_id(self) -> str | None:
        return self._active_object_id

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def saved_revision(self) -> int:
        return self._saved_revision

    @property
    def is_dirty(self) -> bool:
        return self._revision != self._saved_revision

    @property
    def object_count(self) -> int:
        return sum(len(layer.objects) for layer in self._layers)

    def mark_saved(self) -> None:
        self._saved_revision = self._revision

    def adopt_new_identity(self, *, title: str | None = None) -> str:
        """Berikan project_id baru (dan judul baru bila diberikan).

        Dipakai oleh Save As: berkas hasil "simpan sebagai" adalah karya yang
        berdiri sendiri. Tanpa identitas baru, unggahan ke BatikCraftWeb
        ditolak karena source_project_id-nya sama dengan berkas asal.
        """

        self._project_id = str(uuid4())
        if title is not None:
            clean = str(title).strip()
            if clean:
                self.update_metadata(title=clean[:160])
        self._record_change()
        return self._project_id

    def update_metadata(
        self,
        *,
        title: str | None = None,
        creator: str | None = None,
        description: str | None = None,
        tags: tuple[str, ...] | None = None,
    ) -> None:
        candidate = replace(
            self._metadata,
            title=self._metadata.title if title is None else title,
            creator=self._metadata.creator if creator is None else creator,
            description=self._metadata.description if description is None else description,
            tags=self._metadata.tags if tags is None else tags,
        )
        if candidate != self._metadata:
            self._metadata = candidate
            self._record_change()

    def update_canvas(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
        background_color: str | None = None,
    ) -> None:
        candidate = replace(
            self._canvas,
            width=self._canvas.width if width is None else width,
            height=self._canvas.height if height is None else height,
            background_color=(
                self._canvas.background_color
                if background_color is None
                else background_color
            ),
        )
        if candidate != self._canvas:
            self._canvas = candidate
            self._record_change()

    def add_layer(
        self,
        layer: Layer,
        *,
        index: int | None = None,
        select: bool = True,
    ) -> None:
        """Insert a unique layer or group into the tree-aware stack."""

        if not isinstance(layer, Layer):
            raise ProjectValidationError("layer must be a Layer value object.")
        if not isinstance(select, bool):
            raise ProjectValidationError("select must be a boolean.")
        if any(existing.layer_id == layer.layer_id for existing in self._layers):
            raise DuplicateLayerError(f"Layer {layer.layer_id} already exists.")
        self._validate_parent(layer.layer_id, layer.parent_id)
        existing_object_ids = {
            item.object_id for existing in self._layers for item in existing.objects
        }
        duplicate_object_ids = existing_object_ids.intersection(
            item.object_id for item in layer.objects
        )
        if duplicate_object_ids:
            raise DuplicateObjectError(
                f"Object {sorted(duplicate_object_ids)[0]} already exists."
            )
        insertion_index = len(self._layers) if index is None else index
        if isinstance(insertion_index, bool) or not isinstance(insertion_index, int):
            raise ProjectValidationError("Layer insertion index must be an integer.")
        if not 0 <= insertion_index <= len(self._layers):
            raise ProjectValidationError("Layer insertion index is out of range.")
        self._layers.insert(insertion_index, layer)
        if select:
            self._active_layer_id = layer.layer_id
            self._active_object_id = None
        self._record_change()

    def get_layer(self, layer_id: str) -> Layer:
        for layer in self._layers:
            if layer.layer_id == layer_id:
                return layer
        raise LayerNotFoundError(f"Layer {layer_id} was not found.")

    def children_of(self, parent_id: str | None) -> tuple[Layer, ...]:
        """Return direct child nodes in document order."""

        if parent_id is not None:
            self.get_layer(parent_id)
        return tuple(layer for layer in self._layers if layer.parent_id == parent_id)

    def descendants_of(self, layer_id: str) -> tuple[Layer, ...]:
        """Return every descendant of a group in document order."""

        self.get_layer(layer_id)
        result: list[Layer] = []
        pending = [layer_id]
        while pending:
            parent = pending.pop(0)
            children = list(self.children_of(parent))
            result.extend(children)
            pending.extend(child.layer_id for child in children)
        return tuple(result)

    def set_layer_parent(self, layer_id: str, parent_id: str | None) -> Layer:
        """Move a layer or subfolder under a folder without changing stack order."""

        index = self._layer_index(layer_id)
        current = self._layers[index]
        self._validate_parent(layer_id, parent_id)
        if current.parent_id == parent_id:
            return current
        updated = current.with_updates(parent_id=parent_id)
        self._layers[index] = updated
        self._record_change()
        return updated

    def update_layer(self, layer_id: str, **changes: Any) -> Layer:
        index = self._layer_index(layer_id)
        if "parent_id" in changes:
            self._validate_parent(layer_id, changes["parent_id"])
        updated = self._layers[index].with_updates(**changes)
        if updated != self._layers[index]:
            self._layers[index] = updated
            self._record_change()
        return updated

    def remove_layer(self, layer_id: str) -> Layer:
        """Remove one empty tree node; callers remove descendants first."""

        if self.children_of(layer_id):
            raise ProjectValidationError(
                "A folder or layer with sublayers cannot be removed before its children."
            )
        index = self._layer_index(layer_id)
        removed = self._layers.pop(index)
        if self._active_layer_id == layer_id:
            self._active_object_id = None
            if not self._layers:
                self._active_layer_id = None
            else:
                replacement_index = min(index, len(self._layers) - 1)
                self._active_layer_id = self._layers[replacement_index].layer_id
        self._record_change()
        return removed

    def reorder_layer(self, layer_id: str, new_index: int) -> None:
        if isinstance(new_index, bool) or not isinstance(new_index, int):
            raise ProjectValidationError("Layer destination index must be an integer.")
        if not 0 <= new_index < len(self._layers):
            raise ProjectValidationError("Layer destination index is out of range.")
        current_index = self._layer_index(layer_id)
        if current_index == new_index:
            return
        layer = self._layers.pop(current_index)
        self._layers.insert(new_index, layer)
        self._record_change()

    def get_object(self, object_id: str) -> LayerObject:
        for layer in self._layers:
            for item in layer.objects:
                if item.object_id == object_id:
                    return item
        raise ObjectNotFoundError(f"Object {object_id} was not found.")

    def object_layer_id(self, object_id: str) -> str:
        for layer in self._layers:
            if any(item.object_id == object_id for item in layer.objects):
                return layer.layer_id
        raise ObjectNotFoundError(f"Object {object_id} was not found.")

    def add_object(
        self,
        layer_id: str,
        item: LayerObject,
        *,
        index: int | None = None,
        select: bool = True,
    ) -> LayerObject:
        """Insert an independently selectable object into a regular layer."""

        if not isinstance(item, LayerObject):
            raise ProjectValidationError("item must be a LayerObject value object.")
        layer_index = self._layer_index(layer_id)
        layer = self._layers[layer_index]
        if layer.node_kind is LayerNodeKind.GROUP:
            raise ProjectValidationError("Objects cannot be added directly to a folder.")
        try:
            self.get_object(item.object_id)
        except ObjectNotFoundError:
            pass
        else:
            raise DuplicateObjectError(f"Object {item.object_id} already exists.")
        objects = list(layer.objects)
        insertion_index = len(objects) if index is None else index
        if isinstance(insertion_index, bool) or not isinstance(insertion_index, int):
            raise ProjectValidationError("Object insertion index must be an integer.")
        if not 0 <= insertion_index <= len(objects):
            raise ProjectValidationError("Object insertion index is out of range.")
        objects.insert(insertion_index, item)
        self._layers[layer_index] = layer.with_updates(objects=tuple(objects))
        if select:
            self._active_layer_id = layer_id
            self._active_object_id = item.object_id
        self._record_change()
        return item

    def update_object(self, object_id: str, **changes: Any) -> LayerObject:
        layer_index, object_index = self._object_indices(object_id)
        layer = self._layers[layer_index]
        objects = list(layer.objects)
        updated = objects[object_index].with_updates(**changes)
        if updated != objects[object_index]:
            objects[object_index] = updated
            self._layers[layer_index] = layer.with_updates(objects=tuple(objects))
            self._record_change()
        return updated

    def remove_object(self, object_id: str) -> LayerObject:
        layer_index, object_index = self._object_indices(object_id)
        layer = self._layers[layer_index]
        objects = list(layer.objects)
        removed = objects.pop(object_index)
        self._layers[layer_index] = layer.with_updates(objects=tuple(objects))
        if self._active_object_id == object_id:
            self._active_object_id = None
            if objects:
                replacement_index = min(object_index, len(objects) - 1)
                self._active_object_id = objects[replacement_index].object_id
        self._record_change()
        return removed

    def move_object(
        self,
        object_id: str,
        target_layer_id: str,
        *,
        index: int | None = None,
    ) -> LayerObject:
        """Move an object between regular layers as one domain operation."""

        source_layer_index, source_object_index = self._object_indices(object_id)
        target_layer_index = self._layer_index(target_layer_id)
        target_layer = self._layers[target_layer_index]
        if target_layer.node_kind is LayerNodeKind.GROUP:
            raise ProjectValidationError("Objects cannot be moved directly into a folder.")
        source_layer = self._layers[source_layer_index]
        source_objects = list(source_layer.objects)
        item = source_objects.pop(source_object_index)
        target_objects = (
            source_objects if source_layer.layer_id == target_layer_id else list(target_layer.objects)
        )
        insertion_index = len(target_objects) if index is None else index
        if not 0 <= insertion_index <= len(target_objects):
            raise ProjectValidationError("Object destination index is out of range.")
        target_objects.insert(insertion_index, item)
        if source_layer.layer_id == target_layer_id:
            self._layers[source_layer_index] = source_layer.with_updates(
                objects=tuple(target_objects)
            )
        else:
            self._layers[source_layer_index] = source_layer.with_updates(
                objects=tuple(source_objects)
            )
            target_layer_index = self._layer_index(target_layer_id)
            target_layer = self._layers[target_layer_index]
            self._layers[target_layer_index] = target_layer.with_updates(
                objects=tuple(target_objects)
            )
        self._active_layer_id = target_layer_id
        self._active_object_id = object_id
        self._record_change()
        return item

    def reorder_object(self, object_id: str, new_index: int) -> None:
        layer_index, object_index = self._object_indices(object_id)
        layer = self._layers[layer_index]
        if not 0 <= new_index < len(layer.objects):
            raise ProjectValidationError("Object destination index is out of range.")
        if object_index == new_index:
            return
        objects = list(layer.objects)
        item = objects.pop(object_index)
        objects.insert(new_index, item)
        self._layers[layer_index] = layer.with_updates(objects=tuple(objects))
        self._record_change()

    def set_active_layer(self, layer_id: str | None) -> None:
        """Set transient layer selection without making the project dirty."""

        if layer_id is not None:
            self.get_layer(layer_id)
        self._active_layer_id = layer_id
        self._active_object_id = None

    def set_active_object(self, object_id: str | None) -> None:
        """Set transient object selection and synchronize its owning layer."""

        if object_id is None:
            self._active_object_id = None
            return
        layer_id = self.object_layer_id(object_id)
        self._active_layer_id = layer_id
        self._active_object_id = object_id

    def is_layer_effectively_visible(self, layer_id: str) -> bool:
        """Return visibility after applying every ancestor folder's state."""

        layer = self.get_layer(layer_id)
        visited: set[str] = set()
        while True:
            if not layer.visible:
                return False
            if layer.parent_id is None:
                return True
            if layer.layer_id in visited:
                return False
            visited.add(layer.layer_id)
            layer = self.get_layer(layer.parent_id)

    def is_layer_effectively_locked(self, layer_id: str) -> bool:
        """Return lock state inherited from ancestor folders."""

        layer = self.get_layer(layer_id)
        visited: set[str] = set()
        while True:
            if layer.locked:
                return True
            if layer.parent_id is None:
                return False
            if layer.layer_id in visited:
                return True
            visited.add(layer.layer_id)
            layer = self.get_layer(layer.parent_id)

    def validate(self) -> tuple[str, ...]:
        issues: list[str] = []
        try:
            UUID(self._project_id)
        except (ValueError, TypeError, AttributeError):
            issues.append("project_id must be a valid UUID.")

        if self._schema_version != CURRENT_SCHEMA_VERSION:
            issues.append(
                "Unsupported schema_version "
                f"{self._schema_version!r}; expected {CURRENT_SCHEMA_VERSION!r}."
            )
        if not isinstance(self._metadata, ProjectMetadata):
            issues.append("metadata must be a ProjectMetadata value object.")
        if not isinstance(self._canvas, CanvasSpec):
            issues.append("canvas must be a CanvasSpec value object.")

        created_is_aware = self._is_aware_datetime(self._created_at)
        updated_is_aware = self._is_aware_datetime(self._updated_at)
        if not created_is_aware:
            issues.append("created_at must be a timezone-aware datetime.")
        if not updated_is_aware:
            issues.append("updated_at must be a timezone-aware datetime.")
        if created_is_aware and updated_is_aware and self._updated_at < self._created_at:
            issues.append("updated_at must not be earlier than created_at.")

        revision_is_int = isinstance(self._revision, int) and not isinstance(
            self._revision, bool
        )
        if not revision_is_int:
            issues.append("revision must be an integer.")
        elif self._revision < 0:
            issues.append("revision must not be negative.")

        saved_revision_is_int = isinstance(self._saved_revision, int) and not isinstance(
            self._saved_revision, bool
        )
        if not saved_revision_is_int:
            issues.append("saved_revision must be an integer.")
        elif self._saved_revision < -1:
            issues.append("saved_revision must be at least -1.")
        elif revision_is_int and self._saved_revision > self._revision:
            issues.append("saved_revision must not exceed revision.")

        valid_layers: list[Layer] = []
        for index, layer in enumerate(self._layers):
            if isinstance(layer, Layer):
                valid_layers.append(layer)
            else:
                issues.append(f"layers[{index}] must be a Layer value object.")
        layer_ids = [layer.layer_id for layer in valid_layers]
        layer_by_id = {layer.layer_id: layer for layer in valid_layers}
        if len(layer_ids) != len(set(layer_ids)):
            issues.append("Layer IDs must be unique within a project.")

        for layer in valid_layers:
            if layer.parent_id is None:
                continue
            parent = layer_by_id.get(layer.parent_id)
            if parent is None:
                issues.append(f"Layer {layer.layer_id} references a missing parent.")
            elif parent.node_kind is not LayerNodeKind.GROUP:
                issues.append(f"Layer {layer.layer_id} parent must be a group node.")

        for layer in valid_layers:
            seen: set[str] = set()
            current = layer
            while current.parent_id is not None:
                if current.layer_id in seen:
                    issues.append("Layer tree must not contain cycles.")
                    break
                seen.add(current.layer_id)
                parent = layer_by_id.get(current.parent_id)
                if parent is None:
                    break
                current = parent

        object_ids = [item.object_id for layer in valid_layers for item in layer.objects]
        if len(object_ids) != len(set(object_ids)):
            issues.append("Object IDs must be unique within a project.")
        if self._active_layer_id is not None and self._active_layer_id not in layer_ids:
            issues.append("active_layer_id must reference an existing layer.")
        if self._active_object_id is not None:
            if self._active_object_id not in object_ids:
                issues.append("active_object_id must reference an existing object.")
            elif self._active_layer_id is None:
                issues.append("active_object_id requires an active layer.")
            else:
                try:
                    owner = self.object_layer_id(self._active_object_id)
                except ObjectNotFoundError:
                    owner = None
                if owner != self._active_layer_id:
                    issues.append("active_object_id must belong to active_layer_id.")
        return tuple(dict.fromkeys(issues))

    def assert_valid(self) -> None:
        issues = self.validate()
        if issues:
            raise ProjectValidationError(issues)

    def _layer_index(self, layer_id: str) -> int:
        for index, layer in enumerate(self._layers):
            if layer.layer_id == layer_id:
                return index
        raise LayerNotFoundError(f"Layer {layer_id} was not found.")

    def _object_indices(self, object_id: str) -> tuple[int, int]:
        for layer_index, layer in enumerate(self._layers):
            for object_index, item in enumerate(layer.objects):
                if item.object_id == object_id:
                    return layer_index, object_index
        raise ObjectNotFoundError(f"Object {object_id} was not found.")

    def _validate_parent(self, layer_id: str, parent_id: str | None) -> None:
        if parent_id is None:
            return
        if parent_id == layer_id:
            raise ProjectValidationError("A layer cannot be its own parent.")
        parent = self.get_layer(parent_id)
        if parent.node_kind is not LayerNodeKind.GROUP:
            raise ProjectValidationError("A parent node must be a folder/group.")
        current = parent
        visited: set[str] = set()
        while current.parent_id is not None:
            if current.layer_id == layer_id:
                raise ProjectValidationError("Moving this node would create a cycle.")
            if current.layer_id in visited:
                raise ProjectValidationError("Layer tree contains a cycle.")
            visited.add(current.layer_id)
            current = self.get_layer(current.parent_id)
        if current.layer_id == layer_id:
            raise ProjectValidationError("Moving this node would create a cycle.")

    def _record_change(self) -> None:
        self._revision += 1
        self._updated_at = datetime.now(UTC)

    @staticmethod
    def _is_aware_datetime(value: object) -> bool:
        return (
            isinstance(value, datetime)
            and value.tzinfo is not None
            and value.utcoffset() is not None
        )
