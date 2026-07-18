"""Shim kompatibilitas; implementasi ada di ``context_tool_editor_hotfixes``."""

from .context_tool_editor_hotfixes import (  # noqa: F401
    _HotfixV11 as ContextToolEditorWorkspaceView,
    _delete_menu_command,
    _AI_CONTEXT_LABEL,
    _NON_AI_CONTEXT_LABEL,
)

__all__ = ["ContextToolEditorWorkspaceView"]
