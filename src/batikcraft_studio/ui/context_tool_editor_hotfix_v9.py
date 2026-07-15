"""Selected-object recolor and preview-first AI Batik background generation."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from batikcraft_studio.application import (
    AIBatikBackgroundProjectSession,
    DirectStyleProjectSession,
    ProjectSessionError,
)
from batikcraft_studio.assets import AssetLibraryError, PersonalAssetStore
from batikcraft_studio.imaging import BatikAssetError, load_batik_asset

from .ai_batik_background_dialog import AIBatikBackgroundDialog
from .context_tool_editor_hotfix_v8 import ContextToolEditorWorkspaceView as _HotfixV8Editor


def apply_palette_color_to_current_selection(
    session: DirectStyleProjectSession,
    color: str,
) -> tuple[object, ...]:
    """Apply a clicked primary palette color to the current object selection."""

    if not session.has_project or not session.selected_object_ids:
        return ()
    return tuple(session.apply_color_to_selected(color, target="auto"))


class ContextToolEditorWorkspaceView(_HotfixV8Editor):
    """Make palette clicks recolor selection and expose AI background generation."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._background_ai_destroyed = False
        super().__init__(*args, **kwargs)
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label="AI Batik Background…",
            command=self.generate_ai_batik_background,
        )
        self.bind_all(
            "<Control-Alt-g>",
            self._on_ai_background_shortcut,
            add="+",
        )
        self._background_ai_button = ttk.Button(
            self.palette_host,
            text="AI Background…",
            style="Secondary.TButton",
            command=self.generate_ai_batik_background,
        )
        self._background_ai_button.grid(row=0, column=3, sticky="e", padx=(8, 0))

    def _set_primary_color(self, color: str, *, announce: bool = True) -> None:
        """Set drawing color and immediately recolor the selected compatible object."""

        super()._set_primary_color(color, announce=announce)
        if not announce or not hasattr(self, "session"):
            return
        if not isinstance(self.session, DirectStyleProjectSession):
            return
        try:
            updated = apply_palette_color_to_current_selection(self.session, color)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        if not updated:
            return
        self.refresh_context()
        self.activate_select_tool()
        count = len(updated)
        self.set_status(
            f"Warna {color.upper()} diterapkan ke {count} objek terpilih. "
            "Gunakan Undo untuk kembali."
        )

    def generate_ai_batik_background(self) -> None:
        """Open the Stable Diffusion background dialog and commit only approved output."""

        if not self.session.has_project:
            self.set_status("Buat atau buka project sebelum membuat AI Batik Background.")
            return
        try:
            context = self._background_ai_session.prepare_background_ai_context()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        reference_content, reference_name = self._selected_library_reference()
        dialog = AIBatikBackgroundDialog(
            self,
            reference_content=reference_content,
            reference_name=reference_name,
            render_preview=lambda options, content, name: (
                self._background_ai_session.render_background_ai_preview(
                    context,
                    options,
                    reference_content=content,
                    reference_name=name,
                )
            ),
        )
        self.wait_window(dialog)
        preview = dialog.result
        if preview is None:
            self.set_status("Generasi AI Batik Background dibatalkan. Canvas tidak berubah.")
            return
        try:
            result = self._background_ai_session.commit_background_ai_preview(preview)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        saved = False
        try:
            PersonalAssetStore(self.asset_library).import_image(
                f"ai-batik-background-seed-{preview.options.seed}.png",
                preview.result.content,
                category="ornamen",
            )
        except AssetLibraryError as exc:
            messagebox.showwarning(
                "Background diterapkan, tetapi pustaka gagal diperbarui",
                str(exc),
                parent=self.winfo_toplevel(),
            )
        else:
            saved = True
            try:
                self.refresh_library()
            except (AttributeError, tk.TclError):
                pass

        self.refresh_context()
        suffix = " Hasil juga disimpan ke Gambar Impor Saya." if saved else ""
        self.set_status(
            f"{result.name} diterapkan pada layer paling bawah sebagai background terkunci."
            f"{suffix} Gunakan Undo untuk kembali."
        )

    def _selected_library_reference(self) -> tuple[bytes | None, str | None]:
        if not hasattr(self, "library_list"):
            return None, None
        selection = self.library_list.selection()
        if not selection:
            return None, None
        record = self._library_records.get(selection[0])
        if record is None:
            return None, None
        try:
            payload = self.asset_library.read_asset(record)
            asset = load_batik_asset(
                payload,
                filename=Path(record.relative_path).name,
                default_category=record.category,
            )
        except (AssetLibraryError, BatikAssetError, OSError, ValueError):
            return None, None
        return asset.content, record.name

    def _on_ai_background_shortcut(
        self,
        _event: tk.Event[tk.Misc],
    ) -> str:
        self.generate_ai_batik_background()
        return "break"

    @property
    def _background_ai_session(self) -> AIBatikBackgroundProjectSession:
        if not isinstance(self.session, AIBatikBackgroundProjectSession):
            raise RuntimeError("Editor memerlukan AIBatikBackgroundProjectSession.")
        return self.session

    def destroy(self) -> None:
        self._background_ai_destroyed = True
        try:
            self._background_ai_session.unload_background_ai()
        except (AttributeError, RuntimeError):
            pass
        super().destroy()


__all__ = [
    "ContextToolEditorWorkspaceView",
    "apply_palette_color_to_current_selection",
]
