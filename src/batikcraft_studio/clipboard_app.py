"""Application shell extension for canvas object copy and paste."""

from __future__ import annotations

from batikcraft_studio.i18n import tr

from .app import BatikCraftApplication
from .ui.clipboard_main_window import ClipboardMainWindow
from .ui.keyboard import OBJECT_COPY_SEQUENCE, OBJECT_PASTE_SEQUENCE


class ClipboardBatikCraftApplication(BatikCraftApplication):
    """Reserve Ctrl+C/Ctrl+V for selected canvas objects outside text controls."""

    def _create_main_window(self) -> ClipboardMainWindow:
        return ClipboardMainWindow(
            self.root,
            self.session,
            file_commands={
                "new": self.new_project,
                "open": self.open_project,
                "save": self.save_project,
            },
        )

    def _build_menu(self) -> None:
        super()._build_menu()
        menu_bar = self.root.nametowidget(str(self.root.cget("menu")))
        edit_menu = self.root.nametowidget(str(menu_bar.entrycget(1, "menu")))
        edit_menu.insert_command(
            3,
            label=tr("edit.copy"),
            accelerator="Ctrl+C",
            command=self.main_window.editor_copy,
        )
        edit_menu.insert_command(
            4,
            label=tr("edit.paste"),
            accelerator="Ctrl+V",
            command=self.main_window.editor_paste,
        )
        edit_menu.insert_separator(5)

        draw_menu = self.root.nametowidget(str(menu_bar.entrycget(3, "menu")))
        draw_menu.entryconfigure(0, accelerator="Shift+V")
        draw_menu.entryconfigure(7, accelerator="Shift+C")

        self.root.bind_all(
            OBJECT_COPY_SEQUENCE,
            lambda event: self._run_shortcut(event, self.main_window.editor_copy),
        )
        self.root.bind_all(
            OBJECT_PASTE_SEQUENCE,
            lambda event: self._run_shortcut(event, self.main_window.editor_paste),
        )


__all__ = ["ClipboardBatikCraftApplication"]
