"""Compose Batik cap tools with selectable non-asset shape layers."""

from __future__ import annotations

from .batik_editor import BatikEditorWorkspaceView
from .selectable_shape_editor import SelectableShapeEditorWorkspaceView


class SelectableBatikEditorWorkspaceView(
    BatikEditorWorkspaceView,
    SelectableShapeEditorWorkspaceView,
):
    """Use batik tools while preserving shape-aware canvas selection."""


__all__ = ["SelectableBatikEditorWorkspaceView"]
