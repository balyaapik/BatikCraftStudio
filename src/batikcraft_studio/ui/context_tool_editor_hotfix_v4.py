"""Context-menu entry for deterministic two-object Batification."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.application import (
    NonMLBatificationProjectSession,
    ProjectSessionError,
)

from .context_tool_editor_hotfix_v3 import ContextToolEditorWorkspaceView as _HotfixV3Editor


class ContextToolEditorWorkspaceView(_HotfixV3Editor):
    """Expose motif transfer without requiring an AI model or external service."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label="Batifikasi Non-AI (Objek + Motif)",
            command=self.batify_selected_without_model,
        )
        self.bind_all(
            "<Control-Shift-B>",
            self._on_non_ml_batification_shortcut,
            add="+",
        )

    def batify_selected_without_model(self) -> None:
        """Batify the first selected object using the second selected motif."""

        try:
            result = self._non_ml_batification_session.batify_selected_with_motif()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(
            f"{result.name} dibuat tanpa model. Objek sumber disembunyikan dan tetap dapat di-Undo."
        )

    def _on_non_ml_batification_shortcut(
        self,
        _event: tk.Event[tk.Misc],
    ) -> str:
        self.batify_selected_without_model()
        return "break"

    @property
    def _non_ml_batification_session(self) -> NonMLBatificationProjectSession:
        if not isinstance(self.session, NonMLBatificationProjectSession):
            raise RuntimeError("Editor memerlukan NonMLBatificationProjectSession.")
        return self.session


__all__ = ["ContextToolEditorWorkspaceView"]
