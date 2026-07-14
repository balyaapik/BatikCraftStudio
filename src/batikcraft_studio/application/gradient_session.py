"""Gradient and object-opacity application services.

Gradients are stored non-destructively inside ``LayerObject.properties``
and applied at render time.  Applying a gradient:

* does **not** create a new object;
* does **not** increase the layer object count;
* preserves the existing ``object_id``;
* creates exactly one Undo/Redo history entry.

Object opacity (0–100 %) is already stored in ``LayerObject.opacity``
(0.0–1.0).  This session layer adds a convenience wrapper that uses a
0–100 percentage scale.
"""

from __future__ import annotations

from batikcraft_studio.domain import LayerObject

from .position_lock_session import PositionLockProjectSession
from .session import ProjectSessionError

GRADIENT_KEY = "gradient"
FILL_MODE_KEY = "fill_mode"
_VALID_FILL_MODES = ("solid", "linear_gradient", "radial_gradient")


class GradientProjectSession(PositionLockProjectSession):
    """Add gradient styling and object-level opacity (0–100 %) operations."""

    # ------------------------------------------------------------------
    # Gradient
    # ------------------------------------------------------------------

    def set_object_gradient(
        self,
        object_id: str,
        fill_mode: str,
        gradient: dict | None = None,
    ) -> LayerObject:
        """Apply or remove a gradient from one object (one Undo entry).

        Parameters
        ----------
        object_id
            Target object.
        fill_mode
            ``"solid"``, ``"linear_gradient"``, or ``"radial_gradient"``.
        gradient
            Gradient property dict.  Pass ``None`` to clear the gradient
            (resets to ``fill_mode="solid"``).
        """
        if fill_mode not in _VALID_FILL_MODES:
            raise ProjectSessionError(
                f"fill_mode must be one of {_VALID_FILL_MODES!r}."
            )
        project = self.require_project()
        item = project.get_object(object_id)
        props = dict(item.properties)
        props[FILL_MODE_KEY] = fill_mode
        if gradient is not None:
            props[GRADIENT_KEY] = dict(gradient)
        else:
            props.pop(GRADIENT_KEY, None)
        updated: LayerObject | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_object(object_id, properties=props)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Gradient change did not produce an update.")
        return updated

    def clear_object_gradient(self, object_id: str) -> LayerObject:
        """Remove gradient styling, reverting to solid fill."""
        return self.set_object_gradient(object_id, "solid", gradient=None)

    # ------------------------------------------------------------------
    # Object opacity (0–100 percentage convenience API)
    # ------------------------------------------------------------------

    def set_object_opacity_percent(
        self,
        object_id: str,
        opacity_percent: float,
    ) -> LayerObject:
        """Set object opacity using a 0–100 percentage (one Undo entry).

        The effective opacity formula is preserved::

            effective_opacity = object_opacity × layer_opacity × folder_opacity
        """
        if not isinstance(opacity_percent, (int, float)) or isinstance(opacity_percent, bool):
            raise ProjectSessionError("Opacity must be a number.")
        value = float(opacity_percent)
        if not 0.0 <= value <= 100.0:
            raise ProjectSessionError("Opacity must be between 0 and 100.")
        return self.set_object_opacity(object_id, value / 100.0)


__all__ = [
    "FILL_MODE_KEY",
    "GRADIENT_KEY",
    "GradientProjectSession",
]
