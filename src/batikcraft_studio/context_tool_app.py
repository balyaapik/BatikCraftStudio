"""Application shell for contextual Batik tools and external image insertion."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.ai import get_ai_runtime_store
from batikcraft_studio.i18n import tr

from . import app as app_module
from .direct_style_app import DirectStyleApplication
from .ui.ai_runtime_settings_dialog import AIRuntimeSettingsDialog
from .ui.external_image_i18n import install_external_image_translations

install_external_image_translations()


class ContextToolApplication(DirectStyleApplication):
    """Launch the contextual editor with file, drop, clipboard, and global AI settings."""

    def __init__(self) -> None:
        try:
            from tkinterdnd2 import TkinterDnD
        except ImportError:
            super().__init__()
            return

        # TkinterDnD.Tk.__init__ internally calls tkinter.Tk.__init__. Replacing
        # tkinter.Tk with TkinterDnD.Tk before constructing the root therefore
        # recurses forever. Construct the DnD root first while tkinter.Tk is still
        # the original class, then let the existing application initializer adopt
        # that already-created root through a short-lived factory.
        dnd_root = TkinterDnD.Tk()
        original_tk_factory = app_module.tk.Tk
        app_module.tk.Tk = lambda: dnd_root  # type: ignore[misc,assignment]
        try:
            super().__init__()
        except Exception:
            try:
                dnd_root.destroy()
            except tk.TclError:
                pass
            raise
        finally:
            app_module.tk.Tk = original_tk_factory  # type: ignore[misc,assignment]

    def _build_menu(self) -> None:
        super()._build_menu()
        menu_bar = self.root.nametowidget(str(self.root.cget("menu")))
        edit_menu = self.root.nametowidget(str(menu_bar.entrycget(1, "menu")))
        edit_menu.add_separator()
        edit_menu.add_command(
            label="Preferences → AI & GPU…",
            accelerator="Ctrl+,",
            command=self.open_ai_runtime_settings,
        )

        editor = self.main_window._editor()
        insert_menu = tk.Menu(menu_bar)
        insert_menu.add_command(
            label=tr("insert.image_file"),
            accelerator="Ctrl+Shift+I",
            command=editor.import_external_image_dialog,
        )
        insert_menu.add_command(
            label=tr("insert.image_clipboard"),
            accelerator="Ctrl+V",
            command=editor.paste_external_image,
        )
        menu_bar.insert_cascade(2, label=tr("menu.insert"), menu=insert_menu)

        # Structured Batification already creates the AI Batik menu. Reuse that
        # cascade instead of adding a second top-level "AI" menu with overlapping
        # functions. Unique Stable Diffusion workflows are appended to the same menu.
        ai_index, ai_menu = _find_cascade_menu(
            menu_bar,
            tr("menu.ai"),
            "AI Batik",
            "Batik AI",
            "AI",
        )
        menu_bar.entryconfigure(ai_index, label=tr("menu.ai"))
        ai_menu.add_separator()
        ai_menu.add_command(
            label="Batifikasi Objek dengan Stable Diffusion + LoRA…",
            accelerator="Ctrl+Alt+Shift+B",
            command=editor.batify_selected_with_pretrained_ai,
        )
        ai_menu.add_command(
            label="AI Batik Background…",
            accelerator="Ctrl+Alt+Shift+G",
            command=editor.generate_ai_batik_background,
        )
        ai_menu.add_separator()
        ai_menu.add_command(
            label="Pengaturan AI & GPU…",
            accelerator="Ctrl+,",
            command=self.open_ai_runtime_settings,
        )

        bindings = (
            ("<Control-Shift-i>", editor.import_external_image_dialog),
            ("<Control-Shift-I>", editor.import_external_image_dialog),
            ("<Control-comma>", self.open_ai_runtime_settings),
            ("<Control-Alt-Shift-b>", editor.batify_selected_with_pretrained_ai),
            ("<Control-Alt-Shift-g>", editor.generate_ai_batik_background),
        )
        for sequence, command in bindings:
            self.root.bind_all(
                sequence,
                lambda event, action=command: self._run_shortcut(event, action),
            )

    def open_ai_runtime_settings(self) -> None:
        """Open the one persistent compute profile used by all AI workflows."""

        dialog = AIRuntimeSettingsDialog(
            self.root,
            get_ai_runtime_store(),
            unload_models=self._unload_ai_models,
        )
        self.root.wait_window(dialog)
        settings = dialog.result
        if settings is None:
            return
        offload = "aktif" if settings.effective_cpu_offload else "nonaktif"
        self.main_window.flash_status(
            f"Runtime AI global disimpan: {settings.device} / {settings.precision}; "
            f"CPU offload {offload}."
        )

    def _unload_ai_models(self) -> None:
        """Release cached pipelines without clearing the selected offline LoRA."""

        for method_name in ("unload_pretrained_ai", "unload_background_ai"):
            callback = getattr(self.session, method_name, None)
            if callable(callback):
                callback()
        provider = getattr(self.session, "_batification_provider", None)
        unload = getattr(provider, "unload", None)
        if callable(unload):
            unload()


def _find_cascade_menu(menu_bar: tk.Menu, *labels: str) -> tuple[int, tk.Menu]:
    """Find a top-level cascade by label without depending on a fixed index."""

    expected = {str(label) for label in labels}
    end = menu_bar.index(tk.END)
    if end is not None:
        for index in range(end + 1):
            if menu_bar.type(index) != "cascade":
                continue
            if str(menu_bar.entrycget(index, "label")) not in expected:
                continue
            child = menu_bar.nametowidget(str(menu_bar.entrycget(index, "menu")))
            return index, child
    raise RuntimeError("Menu AI Batik tidak ditemukan.")


__all__ = ["ContextToolApplication"]
