"""Shim kompatibilitas; implementasi ada di ``context_tool_editor_hotfixes``."""

from .context_tool_editor_hotfixes import (  # noqa: F401
    _HotfixV9 as ContextToolEditorWorkspaceView,
    apply_palette_color_to_current_selection,
)

__all__ = ["ContextToolEditorWorkspaceView"]
