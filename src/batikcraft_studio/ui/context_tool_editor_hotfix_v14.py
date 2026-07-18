"""Shim kompatibilitas; implementasi ada di ``context_tool_editor_hotfixes``."""

from .context_tool_editor_hotfixes import (  # noqa: F401
    _HotfixV14 as ContextToolEditorWorkspaceView,
    _BATIKBREW_CONTEXT_LABEL,
)

__all__ = ["ContextToolEditorWorkspaceView"]
