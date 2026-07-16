"""Viewport main window with a visible global operation progress indicator."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from batikcraft_studio.i18n import tr
from batikcraft_studio.progress import ProgressUpdate

from .progress_dialog import _stage_label
from .theme import COLORS
from .viewport_main_window import ViewportMainWindow


class ProgressViewportMainWindow(ViewportMainWindow):
    """Extend the status bar so every existing ``set_busy`` call shows activity."""

    def _build_layout(self) -> None:
        self.pack(fill="both", expand=True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_command_toolbar()

        self.workspace_host = ttk.Frame(self, style="App.TFrame")
        self.workspace_host.grid(row=1, column=0, sticky="nsew")
        self.workspace_host.columnconfigure(0, weight=1)
        self.workspace_host.rowconfigure(0, weight=1)

        status = ttk.Frame(self, style="Status.TFrame", padding=(4, 1))
        status.grid(row=2, column=0, sticky="ew")
        status.columnconfigure(0, weight=1)
        ttk.Label(
            status,
            textvariable=self.status_text,
            style="Status.TLabel",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.operation_progress = ttk.Progressbar(
            status,
            mode="indeterminate",
            length=190,
        )
        self.operation_progress.grid(row=0, column=1, padx=(8, 4))
        self.operation_progress.grid_remove()
        self.operation_percent = tk.StringVar(master=self, value="")
        self.operation_percent_label = ttk.Label(
            status,
            textvariable=self.operation_percent,
            style="Status.TLabel",
            width=7,
            anchor="e",
        )
        self.operation_percent_label.grid(row=0, column=2, sticky="e")
        self.operation_percent_label.grid_remove()
        self._operation_progress_running = False

    def set_busy(self, busy: bool, message: str | None = None) -> None:
        """Show an animated bar for legacy long-running operations."""

        self.parent.configure(cursor="watch" if busy else "")
        if message:
            self.set_status(message)
        elif not busy:
            self.set_status(tr("status.ready"))
        if busy:
            self.operation_progress.configure(mode="indeterminate")
            self.operation_progress.grid()
            self.operation_percent.set("")
            self.operation_percent_label.grid_remove()
            if not self._operation_progress_running:
                self.operation_progress.start(12)
                self._operation_progress_running = True
        else:
            self.clear_operation_progress()
        self.parent.update_idletasks()

    def set_operation_progress(self, update: ProgressUpdate) -> None:
        """Display a determinate or indeterminate operation update in the status bar."""

        self.set_status(f"{_stage_label(update.stage)} — {update.message}")
        self.operation_progress.grid()
        percent = update.percent
        if percent is None:
            self.operation_progress.configure(mode="indeterminate")
            self.operation_percent_label.grid_remove()
            if not self._operation_progress_running:
                self.operation_progress.start(12)
                self._operation_progress_running = True
        else:
            if self._operation_progress_running:
                self.operation_progress.stop()
                self._operation_progress_running = False
            self.operation_progress.configure(mode="determinate", maximum=100, value=percent)
            self.operation_percent.set(f"{percent}%")
            self.operation_percent_label.grid()
        self.parent.configure(cursor="watch")
        self.parent.update_idletasks()

    def clear_operation_progress(self) -> None:
        """Hide the global operation bar and restore the normal cursor."""

        if self._operation_progress_running:
            self.operation_progress.stop()
            self._operation_progress_running = False
        self.operation_progress.grid_remove()
        self.operation_percent_label.grid_remove()
        self.operation_percent.set("")
        self.parent.configure(cursor="")

    @property
    def background_color(self) -> str:
        return COLORS["canvas"]


__all__ = ["ProgressViewportMainWindow"]
