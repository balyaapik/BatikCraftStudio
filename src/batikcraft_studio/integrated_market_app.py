"""Final Studio shell for BatikBrew, image-set training, and NFT asset sales."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from batikcraft_studio.application import ProjectSessionError
from batikcraft_studio.ui.generated_image_clipboard import get_generated_image_clipboard
from batikcraft_studio.ui.image_set_dataset_dialog import ImageSetDatasetStudioWindow
from batikcraft_studio.ui.keyboard import (
    OBJECT_COPY_SEQUENCE,
    OBJECT_PASTE_SEQUENCE,
    event_targets_text_input,
)
from batikcraft_studio.ui.library_asset_nft_dialog import PublishLibraryAssetNFTDialog

from .app_icon import apply_app_icon, prepare_windows_app_identity
from .batikbrew_context_tool_app import ContextToolApplication as _BaseApplication
from .context_tool_app import _find_cascade_menu


class ContextToolApplication(_BaseApplication):
    """Expose complete BatikBrew and marketplace workflows from the menu bar."""

    def __init__(self) -> None:
        # This must run before super().__init__ creates the Tk root window so
        # Windows does not group the app under the generic Python taskbar icon.
        prepare_windows_app_identity()
        super().__init__()
        apply_app_icon(self.root)

    def _build_menu(self) -> None:
        super()._build_menu()
        menu_bar = self.root.nametowidget(str(self.root.cget("menu")))
        editor = self.main_window._editor()

        _ai_index, ai_menu = _find_cascade_menu(
            menu_bar,
            "AI Batik",
            "Batik AI",
            "AI",
        )
        _ensure_command(
            ai_menu,
            label="Generate Motif BatikBrew…",
            command=editor.batify_selected_with_pretrained_ai,
            accelerator="Ctrl+Alt+B",
            preferred_index=0,
        )

        _market_index, marketplace_menu = _find_cascade_menu(menu_bar, "Marketplace")
        _ensure_command(
            marketplace_menu,
            label="Jual Asset Pustaka sebagai NFT…",
            command=self.publish_library_asset_to_web,
            preferred_before="Jual Model ke Marketplace…",
        )

        _training_index, training_menu = _find_cascade_menu(
            menu_bar,
            "Training AI Lokal",
        )
        _replace_or_add_command(
            training_menu,
            old_labels=("Dataset Studio SDXL…", "Set Gambar Training SDXL…"),
            label="Set Gambar Training SDXL…",
            command=self.open_dataset_studio,
            preferred_index=0,
        )

        try:
            _edit_index, edit_menu = _find_cascade_menu(menu_bar, "Edit")
        except RuntimeError:
            edit_menu = None
        if edit_menu is not None:
            _ensure_command(
                edit_menu,
                label="Copy Objek / Hasil AI",
                command=self.copy_canvas_selection,
                accelerator="Ctrl+C",
            )
            _ensure_command(
                edit_menu,
                label="Paste Objek / Hasil AI",
                command=self.paste_canvas_clipboard,
                accelerator="Ctrl+V",
            )

        self.root.bind_all(
            "<Control-Alt-b>",
            lambda event: self._run_canvas_shortcut(
                event,
                editor.batify_selected_with_pretrained_ai,
            ),
        )
        self.root.bind_all(
            "<Control-Alt-B>",
            lambda event: self._run_canvas_shortcut(
                event,
                editor.batify_selected_with_pretrained_ai,
            ),
        )
        self.root.bind_all(OBJECT_COPY_SEQUENCE, self._copy_canvas_shortcut)
        self.root.bind_all("<Control-C>", self._copy_canvas_shortcut)
        self.root.bind_all(OBJECT_PASTE_SEQUENCE, self._paste_canvas_shortcut)
        self.root.bind_all("<Control-V>", self._paste_canvas_shortcut)

    def open_dataset_studio(self) -> None:
        window = ImageSetDatasetStudioWindow(self.root)
        window.focus_set()

    def publish_library_asset_to_web(self) -> None:
        session = self._ensure_web_session()
        if session is None:
            return
        if session.account.role != "creator":
            messagebox.showerror(
                "Akun creator diperlukan",
                "Hanya akun Creator / User yang dapat menjual asset pustaka sebagai NFT.",
                parent=self.root,
            )
            return

        project = self.session.project
        if project is None or project.active_object_id is None:
            messagebox.showerror(
                "Pilih asset pustaka",
                "Pilih satu objek asset pada canvas atau panel layer terlebih dahulu.",
                parent=self.root,
            )
            return
        item = project.get_object(project.active_object_id)
        asset_ref = item.asset_ref
        if not asset_ref or asset_ref not in self.session.assets:
            messagebox.showerror(
                "Asset tidak dapat dijual",
                "Objek aktif tidak memiliki gambar raster yang dapat diunggah sebagai NFT.",
                parent=self.root,
            )
            return

        dialog = PublishLibraryAssetNFTDialog(
            self.root,
            client=self.web_client,
            session=session,
            project=project,
            item=item,
            content=self.session.assets[asset_ref],
        )
        dialog.focus_set()

    def copy_canvas_selection(self) -> None:
        """Copy selected canvas objects and make them the active paste source."""

        get_generated_image_clipboard().clear()
        self.main_window._editor().copy_active_object()

    def paste_canvas_clipboard(self) -> None:
        editor = self.main_window._editor()
        generated = get_generated_image_clipboard().read()
        if generated is not None:
            if self.session.project is None:
                self.main_window.flash_status(
                    "Buat atau buka project sebelum menempel hasil AI."
                )
                return
            try:
                item = self.session.import_raster_object(
                    f"{generated.name}.png",
                    generated.content,
                )
            except (ProjectSessionError, OSError, ValueError) as exc:
                messagebox.showerror(
                    "Paste hasil AI gagal",
                    str(exc),
                    parent=self.root,
                )
                return
            self.main_window.refresh_project_context()
            self.main_window.flash_status(
                f"{item.name} ditempel dari clipboard hasil AI. Ctrl+V dapat digunakan lagi."
            )
            return

        has_object_clipboard = bool(
            getattr(self.session, "has_multi_object_clipboard", False)
            or getattr(self.session, "has_object_clipboard", False)
        )
        if has_object_clipboard:
            editor.paste_object()
            return
        editor.paste_external_image()

    def _copy_canvas_shortcut(self, event: tk.Event[tk.Misc]) -> str | None:
        if event_targets_text_input(event):
            return None
        self.copy_canvas_selection()
        return "break"

    def _paste_canvas_shortcut(self, event: tk.Event[tk.Misc]) -> str | None:
        if event_targets_text_input(event):
            return None
        self.paste_canvas_clipboard()
        return "break"

    @staticmethod
    def _run_canvas_shortcut(
        event: tk.Event[tk.Misc],
        command: object,
    ) -> str | None:
        if event_targets_text_input(event):
            return None
        if callable(command):
            command()
        return "break"


def _ensure_command(
    menu: tk.Menu,
    *,
    label: str,
    command: object,
    accelerator: str = "",
    preferred_index: int | None = None,
    preferred_before: str | None = None,
) -> None:
    end = menu.index(tk.END)
    if end is not None:
        for index in range(int(end) + 1):
            if menu.type(index) != "command":
                continue
            if str(menu.entrycget(index, "label")) == label:
                menu.entryconfigure(
                    index,
                    command=command,
                    accelerator=accelerator,
                )
                return

    options = {"label": label, "command": command}
    if accelerator:
        options["accelerator"] = accelerator
    if preferred_before is not None and end is not None:
        for index in range(int(end) + 1):
            if menu.type(index) == "command" and str(
                menu.entrycget(index, "label")
            ) == preferred_before:
                menu.insert_command(index, **options)
                return
    if preferred_index is not None:
        menu.insert_command(preferred_index, **options)
    else:
        menu.add_command(**options)


def _replace_or_add_command(
    menu: tk.Menu,
    *,
    old_labels: tuple[str, ...],
    label: str,
    command: object,
    preferred_index: int = 0,
) -> None:
    end = menu.index(tk.END)
    if end is not None:
        for index in range(int(end) + 1):
            if menu.type(index) != "command":
                continue
            current = str(menu.entrycget(index, "label"))
            if current in old_labels:
                menu.entryconfigure(index, label=label, command=command)
                return
    menu.insert_command(preferred_index, label=label, command=command)


__all__ = ["ContextToolApplication"]
