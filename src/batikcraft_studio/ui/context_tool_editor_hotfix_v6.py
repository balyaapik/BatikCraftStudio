"""External image insertion through file dialog, OS drag-and-drop, and clipboard."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

from batikcraft_studio.application import ExternalImageProjectSession, ProjectSessionError
from batikcraft_studio.assets import AssetLibraryError, PersonalAssetStore

from .context_tool_editor_hotfix_v5 import ContextToolEditorWorkspaceView as _HotfixV5Editor
from .external_image_io import (
    clipboard_payloads,
    image_dialog_filetypes,
    paths_from_clipboard_text,
    paths_from_drop_data,
    payloads_from_paths,
)


class ContextToolEditorWorkspaceView(_HotfixV5Editor):
    """Make external raster images first-class transformable canvas objects."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._personal_asset_store = PersonalAssetStore(self.asset_library)
        self._external_drop_available = self._register_external_drop_target()

    def import_external_image_dialog(self) -> None:
        """Select one or more supported image files and insert them at canvas center."""

        if not self.session.has_project:
            self.set_status("Buat atau buka proyek sebelum memasukkan gambar.")
            return
        selected = filedialog.askopenfilenames(
            parent=self.winfo_toplevel(),
            title="Insert Gambar",
            filetypes=image_dialog_filetypes(),
        )
        if not selected:
            return
        self._import_external_payloads(
            payloads_from_paths(Path(value) for value in selected),
            position=None,
            source_label="file",
        )

    def paste_external_image(self) -> bool:
        """Insert an OS clipboard image or copied external image files."""

        if not self.session.has_project:
            self.set_status("Buat atau buka proyek sebelum menempel gambar.")
            return False
        payloads = clipboard_payloads()
        if not payloads:
            try:
                text = self.clipboard_get()
            except tk.TclError:
                text = ""
            payloads = payloads_from_paths(paths_from_clipboard_text(text))
        if not payloads:
            self.set_status("Clipboard sistem tidak berisi gambar atau file gambar yang didukung.")
            return False
        self._import_external_payloads(payloads, position=None, source_label="clipboard")
        return True

    def paste_object(self) -> None:
        """Preserve internal object paste; otherwise let Ctrl+V accept external images."""

        if self._external_image_session.has_object_clipboard:
            super().paste_object()
            return
        if not self.paste_external_image():
            super().paste_object()

    def _register_external_drop_target(self) -> bool:
        try:
            from tkinterdnd2 import DND_FILES
        except ImportError:
            return False
        register = getattr(self.canvas, "drop_target_register", None)
        bind = getattr(self.canvas, "dnd_bind", None)
        if not callable(register) or not callable(bind):
            return False
        try:
            register(DND_FILES)
            bind("<<DropEnter>>", self._on_external_drop_enter)
            bind("<<DropLeave>>", self._on_external_drop_leave)
            bind("<<Drop>>", self._on_external_image_drop)
        except tk.TclError:
            return False
        return True

    def _on_external_drop_enter(self, _event: Any) -> str:
        self.canvas.configure(cursor="plus")
        self.set_status("Lepaskan file gambar untuk memasukkannya ke canvas dan pustaka.")
        return "copy"

    def _on_external_drop_leave(self, _event: Any) -> str:
        self.canvas.configure(cursor="arrow")
        return "copy"

    def _on_external_image_drop(self, event: Any) -> str:
        self.canvas.configure(cursor="arrow")
        if not self.session.has_project:
            self.set_status("Buat atau buka proyek sebelum menjatuhkan gambar.")
            return "refuse_drop"
        paths = paths_from_drop_data(self.tk.splitlist, str(getattr(event, "data", "")))
        payloads = payloads_from_paths(paths)
        if not payloads:
            self.set_status("Drop ditolak: tidak ada file gambar yang didukung.")
            return "refuse_drop"
        position = self._drop_project_position(event)
        self._import_external_payloads(payloads, position=position, source_label="drag-and-drop")
        return "copy"

    def _drop_project_position(self, event: Any) -> tuple[float, float] | None:
        if self._preview_scale <= 0:
            return None
        try:
            root_x = float(event.x_root)
            root_y = float(event.y_root)
            canvas_x = root_x - float(self.canvas.winfo_rootx())
            canvas_y = root_y - float(self.canvas.winfo_rooty())
        except (AttributeError, TypeError, ValueError, tk.TclError):
            try:
                canvas_x = float(event.x)
                canvas_y = float(event.y)
            except (AttributeError, TypeError, ValueError):
                return None
        return (
            (canvas_x - self._preview_left) / self._preview_scale,
            (canvas_y - self._preview_top) / self._preview_scale,
        )

    def _import_external_payloads(
        self,
        payloads: tuple[tuple[str, bytes], ...],
        *,
        position: tuple[float, float] | None,
        source_label: str,
    ) -> None:
        if not payloads:
            return
        imported = []
        errors: list[str] = []
        category = str(self.asset_category_value.get() or "ornamen")
        for index, (filename, content) in enumerate(payloads):
            current_position = (
                None
                if position is None
                else (position[0] + index * 20.0, position[1] + index * 20.0)
            )
            try:
                record = self._personal_asset_store.import_image(
                    filename,
                    content,
                    category=category,
                )
                item = self._external_image_session.import_external_image(
                    filename,
                    content,
                    position=current_position,
                    library_key=record.key,
                    category=record.category,
                )
            except (AssetLibraryError, ProjectSessionError, OSError) as exc:
                errors.append(f"{filename}: {exc}")
                continue
            imported.append(item)

        self.asset_library.refresh()
        try:
            self.refresh_library()
        except (AttributeError, tk.TclError):
            pass
        if imported:
            self.refresh_context()
            self.activate_select_tool()
            self.set_status(
                f"{len(imported)} gambar dari {source_label} dimasukkan dan disimpan "
                "ke pustaka Gambar Impor Saya."
            )
        if errors:
            messagebox.showwarning(
                "Sebagian gambar gagal dimasukkan",
                "\n".join(errors[:12]),
                parent=self.winfo_toplevel(),
            )

    @property
    def _external_image_session(self) -> ExternalImageProjectSession:
        if not isinstance(self.session, ExternalImageProjectSession):
            raise RuntimeError("Editor memerlukan ExternalImageProjectSession.")
        return self.session


__all__ = ["ContextToolEditorWorkspaceView"]
