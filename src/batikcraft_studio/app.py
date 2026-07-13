"""Application lifecycle and root-window configuration."""

from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

from batikcraft_studio.application import (
    NoActiveProjectError,
    ProjectPathRequiredError,
    ProjectSession,
)
from batikcraft_studio.persistence import PROJECT_EXTENSION, ProjectArchiveError

from .config import APP_NAME, APP_VERSION, DEFAULT_WINDOW_SIZE, MINIMUM_WINDOW_SIZE
from .ui.dialogs import NewProjectDialog
from .ui.main_window import MainWindow
from .ui.theme import configure_theme


class BatikCraftApplication:
    """Own the Tk root, global menu, project session, and clean shutdown behavior."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry(DEFAULT_WINDOW_SIZE)
        self.root.minsize(*MINIMUM_WINDOW_SIZE)
        self.root.option_add("*tearOff", False)

        configure_theme(self.root)
        self.session = ProjectSession()
        self.main_window = MainWindow(self.root, self.session)
        self._build_menu()
        self.root.protocol("WM_DELETE_WINDOW", self.request_close)

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self.root)

        file_menu = tk.Menu(menu_bar)
        file_menu.add_command(
            label="New Project",
            accelerator="Ctrl+N",
            command=self.new_project,
        )
        file_menu.add_command(
            label="Open Project…",
            accelerator="Ctrl+O",
            command=self.open_project,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Save",
            accelerator="Ctrl+S",
            command=self.save_project,
        )
        file_menu.add_command(
            label="Save As…",
            accelerator="Ctrl+Shift+S",
            command=self.save_project_as,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Close Project",
            accelerator="Ctrl+W",
            command=self.close_project,
        )
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
        self.root.bind_all("<Control-n>", lambda _event: self._run_shortcut(self.new_project))
        self.root.bind_all("<Control-o>", lambda _event: self._run_shortcut(self.open_project))
        self.root.bind_all("<Control-s>", lambda _event: self._run_shortcut(self.save_project))
        self.root.bind_all(
            "<Control-Shift-S>",
            lambda _event: self._run_shortcut(self.save_project_as),
        )
        self.root.bind_all("<Control-w>", lambda _event: self._run_shortcut(self.close_project))
        self.root.bind_all("<Control-l>", lambda _event: self.main_window.focus_navigation())

    def new_project(self) -> None:
        if not self._confirm_project_transition("create a new project"):
            return
        dialog = NewProjectDialog(self.root)
        request = dialog.result
        if request is None:
            return
        self.session.new_project(
            title=request.title,
            creator=request.creator,
            width=request.width,
            height=request.height,
            background_color=request.background_color,
        )
        self.main_window.refresh_project_context()
        self.main_window.show_workspace("editor")
        self.main_window.flash_status(f"Created project: {request.title}")

    def open_project(self) -> None:
        if not self._confirm_project_transition("open another project"):
            return
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Open BatikCraft Project",
            filetypes=(("BatikCraft project", f"*{PROJECT_EXTENSION}"),),
        )
        if not selected:
            return

        self.main_window.set_busy(True, "Opening project…")
        try:
            project = self.session.open_project(selected)
        except (ProjectArchiveError, OSError) as exc:
            messagebox.showerror(
                "Could not open project",
                str(exc),
                parent=self.root,
            )
            self.main_window.set_busy(False, "Open failed")
            return

        self.main_window.set_busy(False)
        self.main_window.refresh_project_context()
        self.main_window.show_workspace("editor")
        self.main_window.flash_status(f"Opened project: {project.metadata.title}")

    def save_project(self) -> bool:
        if not self.session.has_project:
            self.main_window.flash_status("No project is open.")
            return False
        try:
            destination = self.session.save()
        except ProjectPathRequiredError:
            return self.save_project_as()
        except (ProjectArchiveError, OSError, NoActiveProjectError) as exc:
            self._show_save_error(exc)
            return False

        self.main_window.refresh_project_context()
        self.main_window.flash_status(f"Saved project: {destination.name}")
        return True

    def save_project_as(self) -> bool:
        snapshot = self.session.snapshot()
        if not snapshot.has_project:
            self.main_window.flash_status("No project is open.")
            return False
        initial_file = self._default_project_filename(snapshot.title or "untitled")
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save BatikCraft Project As",
            defaultextension=PROJECT_EXTENSION,
            initialfile=initial_file,
            filetypes=(("BatikCraft project", f"*{PROJECT_EXTENSION}"),),
        )
        if not selected:
            return False

        self.main_window.set_busy(True, "Saving project…")
        try:
            destination = self.session.save_as(selected)
        except (ProjectArchiveError, OSError, NoActiveProjectError) as exc:
            self.main_window.set_busy(False, "Save failed")
            self._show_save_error(exc)
            return False

        self.main_window.set_busy(False)
        self.main_window.refresh_project_context()
        self.main_window.flash_status(f"Saved project: {destination.name}")
        return True

    def close_project(self) -> None:
        if not self.session.has_project:
            self.main_window.flash_status("No project is open.")
            return
        if not self._confirm_project_transition("close this project"):
            return
        self.session.close_project()
        self.main_window.refresh_project_context()
        self.main_window.show_workspace("dashboard")
        self.main_window.flash_status("Project closed.")

    def _confirm_project_transition(self, action: str) -> bool:
        snapshot = self.session.snapshot()
        if not snapshot.has_project or not snapshot.dirty:
            return True

        decision = messagebox.askyesnocancel(
            "Unsaved changes",
            (
                f"Save changes to '{snapshot.title}' before you {action}?\n\n"
                "Yes saves the project, No discards the current changes, "
                "and Cancel keeps the project open."
            ),
            parent=self.root,
        )
        if decision is None:
            return False
        if decision:
            return self.save_project()
        return True

    def _show_save_error(self, exc: Exception) -> None:
        messagebox.showerror(
            "Could not save project",
            str(exc),
            parent=self.root,
        )

    @staticmethod
    def _default_project_filename(title: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title.strip()).strip("-.")
        return f"{slug or 'untitled'}{PROJECT_EXTENSION}"

    @staticmethod
    def _run_shortcut(command: Callable[[], object]) -> str:
        command()
        return "break"

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
        if self._confirm_project_transition("exit BatikCraft Studio"):
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
