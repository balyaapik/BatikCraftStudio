"""Project aggregate for editable BatikCraft motif documents."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from batikcraft_studio.domain.errors import (
    DuplicateLayerError,
    LayerNotFoundError,
    ProjectValidationError,
)
from batikcraft_studio.domain.models import (
    CURRENT_SCHEMA_VERSION,
    CanvasSpec,
    Layer,
    ProjectMetadata,
)


class Project:
    """Aggregate root that owns project metadata, canvas, and layer ordering.

    Public value objects are immutable. All document mutations pass through this
    class so validation, timestamps, revision numbers, and dirty-state remain
    consistent.
    """

    __slots__ = (
        "_active_layer_id",
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
        """Return whether document content changed since its last save."""

        return self._revision != self._saved_revision

    def mark_saved(self) -> None:
        """Mark the current revision as persisted without changing document data."""

        self._saved_revision = self._revision

    def update_metadata(
        self,
        *,
        title: str | None = None,
        creator: str | None = None,
        description: str | None = None,
        tags: tuple[str, ...] | None = None,
    ) -> None:
        """Replace selected metadata fields and record a content revision."""

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
        """Replace selected canvas properties and record a content revision."""

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
        """Insert a unique layer into the stack."""

        if not isinstance(layer, Layer):
            raise ProjectValidationError("layer must be a Layer value object.")
        if not isinstance(select, bool):
            raise ProjectValidationError("select must be a boolean.")
        if any(existing.layer_id == layer.layer_id for existing in self._layers):
            raise DuplicateLayerError(f"Layer {layer.layer_id} already exists.")
        insertion_index = len(self._layers) if index is None else index
        if isinstance(insertion_index, bool) or not isinstance(insertion_index, int):
            raise ProjectValidationError("Layer insertion index must be an integer.")
        if not 0 <= insertion_index <= len(self._layers):
            raise ProjectValidationError("Layer insertion index is out of range.")
        self._layers.insert(insertion_index, layer)
        if select:
            self._active_layer_id = layer.layer_id
        self._record_change()

    def get_layer(self, layer_id: str) -> Layer:
        """Return a layer by ID or raise ``LayerNotFoundError``."""

        for layer in self._layers:
            if layer.layer_id == layer_id:
                return layer
        raise LayerNotFoundError(f"Layer {layer_id} was not found.")

    def update_layer(self, layer_id: str, **changes: Any) -> Layer:
        """Replace one layer with a validated updated copy."""

        index = self._layer_index(layer_id)
        updated = self._layers[index].with_updates(**changes)
        if updated != self._layers[index]:
            self._layers[index] = updated
            self._record_change()
        return updated

    def remove_layer(self, layer_id: str) -> Layer:
        """Remove a layer and choose a nearby active layer when necessary."""

        index = self._layer_index(layer_id)
        removed = self._layers.pop(index)
        if self._active_layer_id == layer_id:
            if not self._layers:
                self._active_layer_id = None
            else:
                replacement_index = min(index, len(self._layers) - 1)
                self._active_layer_id = self._layers[replacement_index].layer_id
        self._record_change()
        return removed

    def reorder_layer(self, layer_id: str, new_index: int) -> None:
        """Move a layer to a zero-based stack position."""

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

    def set_active_layer(self, layer_id: str | None) -> None:
        """Set transient layer selection without making the project dirty."""

        if layer_id is not None:
            self.get_layer(layer_id)
        self._active_layer_id = layer_id

    def validate(self) -> tuple[str, ...]:
        """Return all aggregate-level validation issues."""

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
        if len(layer_ids) != len(set(layer_ids)):
            issues.append("Layer IDs must be unique within a project.")
        if self._active_layer_id is not None and self._active_layer_id not in layer_ids:
            issues.append("active_layer_id must reference an existing layer.")
        return tuple(issues)

    def assert_valid(self) -> None:
        """Raise ``ProjectValidationError`` when the aggregate is invalid."""

        issues = self.validate()
        if issues:
            raise ProjectValidationError(issues)

    def _layer_index(self, layer_id: str) -> int:
        for index, layer in enumerate(self._layers):
            if layer.layer_id == layer_id:
                return index
        raise LayerNotFoundError(f"Layer {layer_id} was not found.")

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
