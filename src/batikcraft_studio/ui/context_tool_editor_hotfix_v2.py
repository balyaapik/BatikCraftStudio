"""Shim kompatibilitas; implementasi ada di ``context_tool_editor_hotfixes``."""

from .context_tool_editor_hotfixes import (  # noqa: F401
    _HotfixV2 as ContextToolEditorWorkspaceView,
    _clone_project_for_render,
)

__all__ = ["ContextToolEditorWorkspaceView"]
