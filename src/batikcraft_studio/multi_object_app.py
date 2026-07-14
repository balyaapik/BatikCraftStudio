"""Application shell for multi-object selection and grouping."""

from __future__ import annotations

from batikcraft_studio.i18n import tr

from .offline_ai_app import OfflineAIApplication
from .ui.multi_object_i18n import install_multi_object_translations
from .ui.multi_object_main_window import MultiObjectMainWindow

install_multi_object_translations()


class MultiObjectApplication(OfflineAIApplication):
    """Add standard group shortcuts to the offline AI editor shell."""

    def _create_main_window(self) -> MultiObjectMainWindow:
        return MultiObjectMainWindow(
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
        edit_menu.add_separator()
        edit_menu.add_command(
            label=tr("multi.group"),
            accelerator="Ctrl+G",
            command=self.main_window.group_selected_objects,
        )
        edit_menu.add_command(
            label=tr("multi.ungroup"),
            accelerator="Ctrl+Shift+G",
            command=self.main_window.ungroup_selected_objects,
        )
        self.root.bind_all(
            "<Control-g>",
            lambda event: self._run_shortcut(
                event,
                self.main_window.group_selected_objects,
            ),
        )
        self.root.bind_all(
            "<Control-Shift-G>",
            lambda event: self._run_shortcut(
                event,
                self.main_window.ungroup_selected_objects,
            ),
        )
        self.root.bind_all(
            "<Control-Shift-g>",
            lambda event: self._run_shortcut(
                event,
                self.main_window.ungroup_selected_objects,
            ),
        )


__all__ = ["MultiObjectApplication"]
