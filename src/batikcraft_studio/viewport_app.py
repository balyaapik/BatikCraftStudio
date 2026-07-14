"""Application shell for the zoomable BatikCraft canvas viewport."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.i18n import tr

from .process_app import BatikProcessApplication
from .ui.viewport_i18n import install_viewport_translations
from .ui.viewport_main_window import ViewportMainWindow

install_viewport_translations()


class ViewportApplication(BatikProcessApplication):
    """Add zoom, grid/ruler toggles, and a standard Cut command."""

    def _create_main_window(self) -> ViewportMainWindow:
        return ViewportMainWindow(
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
        edit_menu = _cascade_menu(menu_bar, tr("menu.edit"))
        view_menu = _cascade_menu(menu_bar, tr("menu.view"))

        edit_menu.insert_command(
            3,
            label=tr("edit.cut"),
            accelerator="Ctrl+X",
            command=self.main_window.editor_cut,
        )

        view_menu.add_separator()
        view_menu.add_command(
            label=tr("viewport.zoom_in"),
            accelerator="Ctrl++",
            command=self.main_window.zoom_in,
        )
        view_menu.add_command(
            label=tr("viewport.zoom_out"),
            accelerator="Ctrl+-",
            command=self.main_window.zoom_out,
        )
        view_menu.add_command(
            label=tr("viewport.zoom_fit"),
            accelerator="Ctrl+0",
            command=self.main_window.zoom_fit,
        )
        view_menu.add_command(
            label=tr("viewport.zoom_actual"),
            accelerator="Ctrl+1",
            command=self.main_window.zoom_actual_size,
        )
        view_menu.add_separator()
        self.grid_visible_value = tk.BooleanVar(
            master=self.root,
            value=self.main_window.grid_visible,
        )
        self.ruler_visible_value = tk.BooleanVar(
            master=self.root,
            value=self.main_window.ruler_visible,
        )
        view_menu.add_checkbutton(
            label=tr("viewport.grid"),
            variable=self.grid_visible_value,
            command=lambda: self.main_window.set_grid_visible(
                bool(self.grid_visible_value.get())
            ),
        )
        view_menu.add_checkbutton(
            label=tr("viewport.ruler"),
            variable=self.ruler_visible_value,
            command=lambda: self.main_window.set_ruler_visible(
                bool(self.ruler_visible_value.get())
            ),
        )

        bindings = (
            ("<Control-x>", self.main_window.editor_cut),
            ("<Control-plus>", self.main_window.zoom_in),
            ("<Control-equal>", self.main_window.zoom_in),
            ("<Control-KP_Add>", self.main_window.zoom_in),
            ("<Control-minus>", self.main_window.zoom_out),
            ("<Control-KP_Subtract>", self.main_window.zoom_out),
            ("<Control-0>", self.main_window.zoom_fit),
            ("<Control-1>", self.main_window.zoom_actual_size),
        )
        for sequence, command in bindings:
            self.root.bind_all(
                sequence,
                lambda event, action=command: self._run_shortcut(event, action),
            )


def _cascade_menu(menu_bar: tk.Menu, label: str) -> tk.Menu:
    end = menu_bar.index(tk.END)
    if end is None:
        raise RuntimeError(f"Menu {label!r} tidak ditemukan.")
    for index in range(end + 1):
        if menu_bar.type(index) != "cascade":
            continue
        if str(menu_bar.entrycget(index, "label")) == label:
            return menu_bar.nametowidget(str(menu_bar.entrycget(index, "menu")))
    raise RuntimeError(f"Menu {label!r} tidak ditemukan.")


__all__ = ["ViewportApplication"]
