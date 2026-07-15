"""Context-menu workflow for preview-first raster outline cleanup."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.application import (
    OutlineCleanupProjectSession,
    ProjectSessionError,
)

from .context_tool_editor_hotfix_v7 import ContextToolEditorWorkspaceView as _HotfixV7Editor
from .outline_cleanup_dialog import OutlineCleanupDialog


class ContextToolEditorWorkspaceView(_HotfixV7Editor):
    """Clean one selected image object without changing it before user approval."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label="Rapikan Outline…",
            command=self.clean_selected_outline,
        )
        self.bind_all(
            "<Control-Alt-o>",
            self._on_outline_cleanup_shortcut,
            add="+",
        )

    def clean_selected_outline(self) -> None:
        """Open a modal source/result preview for one selected raster-like object."""

        try:
            plan = self._outline_cleanup_session.prepare_outline_cleanup()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        dialog = OutlineCleanupDialog(
            self,
            source_name=plan.source_object.name,
            source_content=plan.source_content,
            render_preview=lambda options: (
                self._outline_cleanup_session.render_outline_cleanup_preview(plan, options)
            ),
        )
        self.wait_window(dialog)
        preview = dialog.result
        if preview is None:
            self.set_status("Rapikan Outline dibatalkan. Objek pada canvas tidak berubah.")
            return

        try:
            result = self._outline_cleanup_session.commit_outline_cleanup_preview(plan, preview)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.activate_select_tool()
        removed = preview.result.removed_components
        self.set_status(
            f"Outline {result.name} dirapikan; {removed} bercak dihapus. "
            "Gunakan Undo untuk kembali."
        )

    def _on_outline_cleanup_shortcut(
        self,
        _event: tk.Event[tk.Misc],
    ) -> str:
        self.clean_selected_outline()
        return "break"

    @property
    def _outline_cleanup_session(self) -> OutlineCleanupProjectSession:
        if not isinstance(self.session, OutlineCleanupProjectSession):
            raise RuntimeError("Editor memerlukan OutlineCleanupProjectSession.")
        return self.session


__all__ = ["ContextToolEditorWorkspaceView"]
