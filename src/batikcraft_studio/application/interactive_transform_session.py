"""Interactive object transforms that preview live but commit as one history step."""

from __future__ import annotations

from batikcraft_studio.domain import LayerObject, Transform
from batikcraft_studio.imaging.affine_object import SHEAR_X_KEY, SHEAR_Y_KEY

from .asset_edit_session import EditableObjectProjectSession
from .session import HISTORY_LIMIT, ProjectSessionError, _SessionState


class InteractiveTransformProjectSession(EditableObjectProjectSession):
    """Support live canvas transforms without creating one undo entry per mouse move."""

    def __init__(self) -> None:
        super().__init__()
        self._interactive_before: _SessionState | None = None
        self._interactive_object_id: str | None = None

    @property
    def interactive_transform_active(self) -> bool:
        return self._interactive_before is not None

    def set_canvas_background(self, color: str) -> str:
        """Update the project canvas color as one undoable mutation."""

        project = self.require_project()
        previous = project.canvas.background_color
        value = str(color).strip().upper()
        if value == previous:
            return previous
        self._commit_mutation(lambda: project.update_canvas(background_color=value))
        return project.canvas.background_color

    def begin_interactive_object_transform(self, object_id: str) -> LayerObject:
        if self._interactive_before is not None:
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
        shear_x: float | None = None,
        shear_y: float | None = None,
    ) -> LayerObject:
        if self._interactive_before is None or self._interactive_object_id != object_id:
            raise ProjectSessionError("Transformasi interaktif belum dimulai untuk objek ini.")
        project = self.require_project()
        current = self._require_unlocked_object(object_id)
        properties = dict(current.properties)
        if shear_x is not None:
            properties[SHEAR_X_KEY] = float(shear_x)
        if shear_y is not None:
            properties[SHEAR_Y_KEY] = float(shear_y)
        return project.update_object(
            object_id,
            transform=transform,
            properties=properties,
        )

    def commit_interactive_object_transform(self) -> bool:
        before = self._interactive_before
        if before is None:
            return False
        changed = before.project is not None and self._project is not None and (
            before.project.revision != self._project.revision
        )
        if changed:
            self._undo_stack.append(before)
            if len(self._undo_stack) > HISTORY_LIMIT:
                del self._undo_stack[0]
            self._redo_stack.clear()
        self._interactive_before = None
        self._interactive_object_id = None
        return changed

    def cancel_interactive_object_transform(self) -> bool:
        before = self._interactive_before
        if before is None:
            return False
        self._restore_state(before)
        self._interactive_before = None
        self._interactive_object_id = None
        return True


__all__ = ["InteractiveTransformProjectSession"]
