"""Application shell for contextual Batik tools and external image insertion."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.i18n import tr

from . import app as app_module
from .direct_style_app import DirectStyleApplication
from .ui.external_image_i18n import install_external_image_translations

install_external_image_translations()


class ContextToolApplication(DirectStyleApplication):
    """Launch the contextual editor with file, drop, and clipboard image insertion."""

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
        insert_menu = tk.Menu(menu_bar)
        insert_menu.add_command(
            label=tr("insert.image_file"),
            accelerator="Ctrl+Shift+I",
            command=self.main_window._editor().import_external_image_dialog,
        )
        insert_menu.add_command(
            label=tr("insert.image_clipboard"),
            accelerator="Ctrl+V",
            command=self.main_window._editor().paste_external_image,
        )
        menu_bar.insert_cascade(2, label=tr("menu.insert"), menu=insert_menu)
        self.root.bind_all(
            "<Control-Shift-i>",
            lambda event: self._run_shortcut(
                event,
                self.main_window._editor().import_external_image_dialog,
            ),
        )
        self.root.bind_all(
            "<Control-Shift-I>",
            lambda event: self._run_shortcut(
                event,
                self.main_window._editor().import_external_image_dialog,
            ),
        )


__all__ = ["ContextToolApplication"]