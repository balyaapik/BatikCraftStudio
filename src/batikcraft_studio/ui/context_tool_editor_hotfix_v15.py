"""Shim kompatibilitas; implementasi ada di ``context_tool_editor_hotfixes``."""

from .context_tool_editor_hotfixes import (  # noqa: F401
    ContextToolEditorWorkspaceView as ContextToolEditorWorkspaceView,
)

__all__ = ["ContextToolEditorWorkspaceView"]
