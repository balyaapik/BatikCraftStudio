"""Interactive WYSIWYG object transforms with one-step Undo/Redo."""

from __future__ import annotations

import math

from batikcraft_studio.domain import LayerObject, Transform

from .asset_edit_session import EditableObjectProjectSession
from .session import ProjectSessionError, _SessionState

_MAX_SHEAR = 8.0
_MIN_DETERMINANT = 1e-4


class InteractiveTransformProjectSession(EditableObjectProjectSession):
    """Support live transform previews while committing one history entry."""

    def __init__(self) -> None:
        super().__init__()
        self._interactive_before: _SessionState | None = None
        self._interactive_object_id: str | None = None

    def update_object_transform(
        self,
        object_id: str,
        *,
        x: float | None = None,
        y: float | None = None,
        rotation_degrees: float | None = None,
        scale_x: float | None = None,
        scale_y: float | None = None,
        shear_x: float | None = None,
        shear_y: float | None = None,
    ) -> LayerObject:
        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        transform, properties = self._transform_candidate(
            item,
            x=x,
            y=y,
            rotation_degrees=rotation_degrees,
            scale_x=scale_x,
            scale_y=scale_y,
            shear_x=shear_x,
            shear_y=shear_y,
        )
        if transform == item.transform and properties == dict(item.properties):
            return item
        updated: LayerObject | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_object(
                object_id,
                transform=transform,
                properties=properties,
            )

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Transform objek tidak menghasilkan perubahan.")
        return updated

    def begin_interactive_object_transform(self, object_id: str) -> LayerObject:
        self.cancel_interactive_object_transform()
        item = self._require_unlocked_object(object_id)
        self._interactive_before = self._capture_state()
        self._interactive_object_id = object_id
        return item

    def preview_interactive_object_transform(
        self,
        object_id: str,
        *,
        transform: Transform,
        shear_x: float,
        shear_y: float,
    ) -> LayerObject:
        if self._interactive_before is None or self._interactive_object_id != object_id:
            raise ProjectSessionError("Transform interaktif belum dimulai.")
        self._restore_state(self._interactive_before)
        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        properties = self._validated_shear_properties(item, shear_x, shear_y)
        return project.update_object(
            object_id,
            transform=transform,
            properties=properties,
        )

    def commit_interactive_object_transform(
        self,
        object_id: str,
        *,
        transform: Transform,
        shear_x: float,
        shear_y: float,
    ) -> LayerObject:
        if self._interactive_before is None or self._interactive_object_id != object_id:
            raise ProjectSessionError("Transform interaktif belum dimulai.")
        before = self._interactive_before
        self._interactive_before = None
        self._interactive_object_id = None
        self._restore_state(before)
        return self.update_object_transform(
            object_id,
            x=transform.x,
            y=transform.y,
            rotation_degrees=transform.rotation_degrees,
            scale_x=transform.scale_x,
            scale_y=transform.scale_y,
            shear_x=shear_x,
            shear_y=shear_y,
        )

    def cancel_interactive_object_transform(self) -> None:
        if self._interactive_before is not None:
            self._restore_state(self._interactive_before)
        self._interactive_before = None
        self._interactive_object_id = None

    def _transform_candidate(
        self,
        item: LayerObject,
        *,
        x: float | None,
        y: float | None,
        rotation_degrees: float | None,
        scale_x: float | None,
        scale_y: float | None,
        shear_x: float | None,
        shear_y: float | None,
    ) -> tuple[Transform, dict[str, object]]:
        current = item.transform
        transform = Transform(
            x=current.x if x is None else x,
            y=current.y if y is None else y,
            rotation_degrees=(
                current.rotation_degrees
                if rotation_degrees is None
                else rotation_degrees
            ),
            scale_x=current.scale_x if scale_x is None else scale_x,
            scale_y=current.scale_y if scale_y is None else scale_y,
        )
        current_shear_x = float(item.properties.get("shear_x", 0.0))
        current_shear_y = float(item.properties.get("shear_y", 0.0))
        properties = self._validated_shear_properties(
            item,
            current_shear_x if shear_x is None else shear_x,
            current_shear_y if shear_y is None else shear_y,
        )
        return transform, properties

    @staticmethod
    def _validated_shear_properties(
        item: LayerObject,
        shear_x: float,
        shear_y: float,
    ) -> dict[str, object]:
        values = (float(shear_x), float(shear_y))
        if any(not math.isfinite(value) for value in values):
            raise ProjectSessionError("Nilai shear harus berupa angka finite.")
        if any(abs(value) > _MAX_SHEAR for value in values):
            raise ProjectSessionError(f"Nilai shear harus berada antara -{_MAX_SHEAR:g} dan {_MAX_SHEAR:g}.")
        if abs(1.0 - values[0] * values[1]) < _MIN_DETERMINANT:
            raise ProjectSessionError("Kombinasi shear menghasilkan transform singular.")
        properties = dict(item.properties)
        properties["shear_x"] = values[0]
        properties["shear_y"] = values[1]
        return properties


__all__ = ["InteractiveTransformProjectSession"]
