"""Application shell for Milestone 4A Structured Batification."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.i18n import tr

from .clipboard_app import ClipboardBatikCraftApplication
from .ui.structured_batification_i18n import (
    install_structured_batification_translations,
)
from .ui.structured_batification_main_window import StructuredBatificationMainWindow

install_structured_batification_translations()


class StructuredBatificationApplication(ClipboardBatikCraftApplication):
    """Add source-preserving Batik render commands to the desktop shell."""

    def _create_main_window(self) -> StructuredBatificationMainWindow:
        return StructuredBatificationMainWindow(
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
        ai_menu = tk.Menu(menu_bar)
        ai_menu.add_command(
            label=tr("ai.batify_object"),
            accelerator="Ctrl+Alt+B",
            command=self.main_window.batify_selected_object,
        )
        ai_menu.add_command(
            label=tr("ai.batify_group"),
            accelerator="Ctrl+Alt+G",
            command=self.main_window.batify_selected_group,
        )
        ai_menu.add_separator()
        ai_menu.add_command(
            label=tr("ai.rerender"),
            accelerator="Ctrl+Alt+R",
            command=self.main_window.rerender_selected_component,
        )
        ai_menu.add_command(
            label=tr("ai.show_source"),
            command=self.main_window.show_selected_source,
        )
        ai_menu.add_command(
            label=tr("ai.show_latest"),
            command=self.main_window.show_selected_latest_render,
        )
        ai_menu.add_separator()
        ai_menu.add_command(
            label=tr("ai.reset"),
            command=self.main_window.reset_selected_batification,
        )
        menu_bar.insert_cascade(5, label=tr("menu.ai"), menu=ai_menu)

        bindings = (
            ("<Control-Alt-b>", self.main_window.batify_selected_object),
            ("<Control-Alt-g>", self.main_window.batify_selected_group),
            ("<Control-Alt-r>", self.main_window.rerender_selected_component),
        )
        for sequence, command in bindings:
            self.root.bind_all(
                sequence,
                lambda event, action=command: self._run_shortcut(event, action),
            )


__all__ = ["StructuredBatificationApplication"]
