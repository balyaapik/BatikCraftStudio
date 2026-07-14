"""Application shell for context grouping and Batik process planning."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.i18n import tr

from .multi_object_app import MultiObjectApplication
from .ui.process_i18n import install_process_translations
from .ui.process_main_window import BatikProcessMainWindow

install_process_translations()


class BatikProcessApplication(MultiObjectApplication):
    """Add a production menu without changing the editor's manual workflow."""

    def _create_main_window(self) -> BatikProcessMainWindow:
        return BatikProcessMainWindow(
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
        production_menu = tk.Menu(menu_bar)
        production_menu.add_command(
            label=tr("process.studio"),
            accelerator="Ctrl+Alt+P",
            command=self.main_window.open_batik_process_studio,
        )
        menu_bar.add_cascade(label=tr("menu.production"), menu=production_menu)
        self.root.bind_all(
            "<Control-Alt-p>",
            lambda event: self._run_shortcut(
                event,
                self.main_window.open_batik_process_studio,
            ),
        )


__all__ = ["BatikProcessApplication"]
