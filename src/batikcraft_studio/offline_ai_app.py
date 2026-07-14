"""Application shell for fully offline LoRA Batification."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.i18n import tr

from .structured_batification_app import StructuredBatificationApplication
from .ui.offline_ai_i18n import install_offline_ai_translations
from .ui.offline_ai_main_window import OfflineAIMainWindow

install_offline_ai_translations()


class OfflineAIApplication(StructuredBatificationApplication):
    """Add Dataset Studio, offline model packs, and rectangle selection."""

    def _create_main_window(self) -> OfflineAIMainWindow:
        return OfflineAIMainWindow(
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
        ai_menu = self.root.nametowidget(str(menu_bar.entrycget(5, "menu")))
        ai_menu.insert_command(
            0,
            label=tr("offline.selection.menu"),
            accelerator="Ctrl+Alt+S",
            command=self.main_window.begin_ai_rectangle_selection,
        )
        ai_menu.insert_separator(1)
        ai_menu.add_separator()
        ai_menu.add_command(
            label=tr("offline.dataset.menu"),
            command=self.main_window.open_dataset_studio,
        )
        ai_menu.add_command(
            label=tr("offline.models.menu"),
            command=self.main_window.open_offline_model_manager,
        )
        self.root.bind_all(
            "<Control-Alt-s>",
            lambda event: self._run_shortcut(
                event,
                self.main_window.begin_ai_rectangle_selection,
            ),
        )


__all__ = ["OfflineAIApplication"]
