"""Context-menu entry for preview-first deterministic Batification."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.application import (
    NonMLBatificationProjectSession,
    ProjectSessionError,
)
from batikcraft_studio.assets import PersonalAssetStore

from .context_tool_editor_hotfix_v3 import ContextToolEditorWorkspaceView as _HotfixV3Editor
from .non_ml_batification_dialog import NonMLBatificationDialog


class ContextToolEditorWorkspaceView(_HotfixV3Editor):
    """Preview motif transfer before replacing the selected object's pixels."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label="Batifikasi Non-AI…",
            command=self.batify_selected_without_model,
        )
        self.bind_all(
            "<Control-Shift-B>",
            self._on_non_ml_batification_shortcut,
            add="+",
        )

    def batify_selected_without_model(self) -> None:
        """Open a modal preview dialog for the first selected canvas object."""

        try:
            plan = self._non_ml_batification_session.prepare_non_ml_batification()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        dialog = NonMLBatificationDialog(
            self,
            source_name=plan.source_object.name,
            source_content=plan.source_content,
            asset_library=self.asset_library,
            personal_store=PersonalAssetStore(self.asset_library),
            render_preview=lambda motif, name, key, options: (
                self._non_ml_batification_session.render_non_ml_batification_preview(
                    plan,
                    motif,
                    motif_name=name,
                    motif_library_key=key,
                    options=options,
                )
            ),
        )
        self.wait_window(dialog)

        self.asset_library.refresh()
        try:
            self.refresh_library()
        except (AttributeError, tk.TclError):
            pass
        preview = dialog.result
        if preview is None:
            self.set_status("Batifikasi Non-AI dibatalkan. Objek pada canvas tidak berubah.")
            return

        try:
            result = self._non_ml_batification_session.commit_non_ml_batification_preview(
                plan,
                preview,
            )
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.activate_select_tool()
        self.set_status(
            f"{result.name} diterapkan setelah preview disetujui. Gunakan Undo untuk kembali."
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
