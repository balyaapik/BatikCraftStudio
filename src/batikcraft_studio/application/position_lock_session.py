"""Position-lock application service layered on ViewportProjectSession.

Position lock stores ``"position_locked": True`` inside
``LayerObject.properties``.  The schema version is unchanged — it fits
inside the existing flexible ``properties`` mapping.

Position lock is distinct from the existing *layer* lock and the existing
*object* ``locked`` flag:

* ``layer.locked`` — prevents editing the entire layer.
* ``object.locked`` — prevents all structural edits including color/opacity.
* ``object.properties["position_locked"]`` — blocks x/y changes only;
  color, opacity, gradient, resize, rotation, cut/copy/duplicate remain
  fully available.
"""

from __future__ import annotations

from .session import ProjectSessionError
from .viewport_session import ViewportProjectSession

POSITION_LOCK_KEY = "position_locked"


class PositionLockedError(ProjectSessionError):
    """Raised when a move operation targets a position-locked object."""


class PositionLockProjectSession(ViewportProjectSession):
    """Add per-object position-lock commands above the viewport session."""

    def lock_object_position(self, object_id: str) -> None:
        """Lock the x/y position of one object (one Undo/Redo entry)."""
        project = self.require_project()
        item = project.get_object(object_id)
        if item.properties.get(POSITION_LOCK_KEY):
            return  # Already locked — idempotent.
        props = dict(item.properties)
        props[POSITION_LOCK_KEY] = True

        def mutation() -> None:
            project.update_object(object_id, properties=props)

        self._commit_mutation(mutation)

    def unlock_object_position(self, object_id: str) -> None:
        """Unlock the x/y position of one object (one Undo/Redo entry)."""
        project = self.require_project()
        item = project.get_object(object_id)
        if not item.properties.get(POSITION_LOCK_KEY):
            return  # Already unlocked — idempotent.
        props = {k: v for k, v in item.properties.items() if k != POSITION_LOCK_KEY}

        def mutation() -> None:
            project.update_object(object_id, properties=props)

        self._commit_mutation(mutation)

    def is_position_locked(self, object_id: str) -> bool:
        """Return True if the object's position is currently locked."""
        project = self.require_project()
        item = project.get_object(object_id)
        return bool(item.properties.get(POSITION_LOCK_KEY))

    # ------------------------------------------------------------------
    # Override movement operations to respect position lock
    # ------------------------------------------------------------------

    def move_object(self, object_id: str, *, x: float, y: float):  # type: ignore[override]
        """Move an object, raising PositionLockedError if locked."""
        self._require_position_unlocked(object_id)
        return super().move_object(object_id, x=x, y=y)

    def update_object_transform(  # type: ignore[override]
        self,
        object_id: str,
        *,
        x: float | None = None,
        y: float | None = None,
        rotation_degrees: float | None = None,
        scale_x: float | None = None,
        scale_y: float | None = None,
    ):
        """Apply a transform, rejecting x/y changes when position is locked."""
        if (x is not None or y is not None) and self.is_position_locked(object_id):
            raise PositionLockedError(
                "Object position is locked. "
                "Unlock it first before changing x or y."
            )
        return super().update_object_transform(
            object_id,
            x=x,
            y=y,
            rotation_degrees=rotation_degrees,
            scale_x=scale_x,
            scale_y=scale_y,
        )

    def begin_interactive_multi_move(  # type: ignore[override]
        self,
        object_ids=None,
    ):
        """Reject multi-move if any participating object has position locked."""
        ids = (
            tuple(object_ids)
            if object_ids is not None
            else self.selected_object_ids
        )
        project = self.require_project()
        locked_names = [
            project.get_object(oid).name
            for oid in ids
            if project.get_object(oid).properties.get(POSITION_LOCK_KEY)
        ]
        if locked_names:
            joined = ", ".join(f"'{n}'" for n in locked_names)
            raise PositionLockedError(
                f"Cannot move selection: the following objects have their "
                f"positions locked: {joined}."
            )
        return super().begin_interactive_multi_move(object_ids)

    def preview_interactive_multi_move(self, delta_x: float, delta_y: float):  # type: ignore[override]
        """Prevent preview updates when any selected object is position-locked."""
        for object_id in self._multi_move_originals:
            if self.is_position_locked(object_id):
                raise PositionLockedError(
                    "Cannot move selection: at least one object has its "
                    "position locked."
                )
        return super().preview_interactive_multi_move(delta_x, delta_y)

    # ------------------------------------------------------------------
    # Keyboard arrow move
    # ------------------------------------------------------------------

    def nudge_selected_objects(
        self,
        delta_x: float,
        delta_y: float,
    ) -> tuple:
        """Move selected objects by a small delta, respecting position lock."""
        ids = self.selected_object_ids
        if not ids:
            raise ProjectSessionError("No objects selected.")
        project = self.require_project()
        locked = [
            project.get_object(oid).name
            for oid in ids
            if project.get_object(oid).properties.get(POSITION_LOCK_KEY)
        ]
        if locked:
            joined = ", ".join(f"'{n}'" for n in locked)
            raise PositionLockedError(
                f"Cannot nudge: the following objects have their positions "
                f"locked: {joined}."
            )
        updated = []
        for oid in ids:
            item = project.get_object(oid)
            updated.append(
                self.update_object_transform(
                    oid,
                    x=item.transform.x + delta_x,
                    y=item.transform.y + delta_y,
                )
            )
        return tuple(updated)

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _require_position_unlocked(self, object_id: str) -> None:
        if self.is_position_locked(object_id):
            project = self.require_project()
            name = project.get_object(object_id).name
            raise PositionLockedError(
                f"Object {name!r} cannot be moved because its position is locked."
            )


__all__ = [
    "POSITION_LOCK_KEY",
    "PositionLockedError",
    "PositionLockProjectSession",
]
