"""Application lifecycle and root-window configuration."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .config import APP_NAME, APP_VERSION, DEFAULT_WINDOW_SIZE, MINIMUM_WINDOW_SIZE
from .ui.main_window import MainWindow
from .ui.theme import configure_theme


class BatikCraftApplication:
    """Own the Tk root, global menu, theme, and clean shutdown behavior."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry(DEFAULT_WINDOW_SIZE)
        self.root.minsize(*MINIMUM_WINDOW_SIZE)
        self.root.option_add("*tearOff", False)

        configure_theme(self.root)
        self.main_window = MainWindow(self.root)
        self._build_menu()
        self.root.protocol("WM_DELETE_WINDOW", self.request_close)

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self.root)

        file_menu = tk.Menu(menu_bar)
        file_menu.add_command(
            label="New Project",
            accelerator="Ctrl+N",
            command=lambda: self._announce_future_feature("New Project", "Milestone 2"),
        )
        file_menu.add_command(
            label="Open Project…",
            accelerator="Ctrl+O",
            command=lambda: self._announce_future_feature("Open Project", "Milestone 2"),
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.request_close)
        menu_bar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menu_bar)
        view_menu.add_command(
            label="Focus Navigation",
            accelerator="Ctrl+L",
            command=self.main_window.focus_navigation,
        )
        for index, workspace in enumerate(
            ("dashboard", "editor", "batikification", "preview", "publish"),
            start=1,
        ):
            view_menu.add_command(
                label=f"Workspace {index}",
                accelerator=f"Ctrl+{index}",
                command=lambda key=workspace: self.main_window.show_workspace(key),
            )
        menu_bar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menu_bar)
        help_menu.add_command(label="About BatikCraft Studio", command=self.show_about)
        menu_bar.add_cascade(label="Help", menu=help_menu)

        self.root.configure(menu=menu_bar)
        self.root.bind_all(
            "<Control-n>",
            lambda _event: self._announce_future_feature("New Project", "Milestone 2"),
        )
        self.root.bind_all(
            "<Control-o>",
            lambda _event: self._announce_future_feature("Open Project", "Milestone 2"),
        )
        self.root.bind_all("<Control-l>", lambda _event: self.main_window.focus_navigation())

    def _announce_future_feature(self, feature: str, milestone: str) -> None:
        self.main_window.flash_status(f"{feature} is scheduled for {milestone}.")

    def show_about(self) -> None:
        messagebox.showinfo(
            f"About {APP_NAME}",
            (
                f"{APP_NAME} {APP_VERSION}\n\n"
                "A native workspace for manual and AI-assisted batik motif creation.\n\n"
                "The application is being implemented incrementally so each feature "
                "can be reviewed and refined with IBM Bob."
            ),
            parent=self.root,
        )

    def request_close(self) -> None:
        """Central shutdown point; dirty-project checks will be added in Milestone 2."""

        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
