"""Main window with a visible progress indicator for legacy busy operations."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from batikcraft_studio.i18n import tr

from .viewport_main_window import ViewportMainWindow


class ProgressViewportMainWindow(ViewportMainWindow):
    """Turn every existing ``set_busy`` call into visible activity feedback."""

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
        self.busy_progress = ttk.Progressbar(
            status,
            mode="indeterminate",
            length=190,
        )
        self.busy_progress.grid(row=0, column=1, padx=(8, 4))
        self.busy_progress.grid_remove()
        self.busy_percent = tk.StringVar(master=self, value="")
        self.busy_percent_label = ttk.Label(
            status,
            textvariable=self.busy_percent,
            style="Status.TLabel",
            width=7,
            anchor="e",
        )
        self.busy_percent_label.grid(row=0, column=2, sticky="e")
        self.busy_percent_label.grid_remove()
        self._busy_progress_running = False

    def set_busy(self, busy: bool, message: str | None = None) -> None:
        """Display an animated bar while older synchronous workflows are active."""

        self.parent.configure(cursor="watch" if busy else "")
        if message:
            self.set_status(message)
        elif not busy:
            self.set_status(tr("status.ready"))
        if busy:
            self.busy_progress.configure(mode="indeterminate")
            self.busy_progress.grid()
            self.busy_percent_label.grid_remove()
            if not self._busy_progress_running:
                self.busy_progress.start(12)
                self._busy_progress_running = True
        else:
            self.clear_busy_progress()
        self.parent.update_idletasks()

    def set_busy_fraction(
        self,
        completed: float,
        total: float,
        message: str | None = None,
    ) -> None:
        """Show determinate progress for callers that know their total work."""

        if message:
            self.set_status(message)
        if self._busy_progress_running:
            self.busy_progress.stop()
            self._busy_progress_running = False
        total_value = max(1.0, float(total))
        percent = round(max(0.0, min(float(completed), total_value)) / total_value * 100)
        self.busy_progress.configure(mode="determinate", maximum=100, value=percent)
        self.busy_progress.grid()
        self.busy_percent.set(f"{percent}%")
        self.busy_percent_label.grid()
        self.parent.configure(cursor="watch")
        self.parent.update_idletasks()

    def clear_busy_progress(self) -> None:
        """Hide the progress bar and restore the normal cursor."""

        if self._busy_progress_running:
            self.busy_progress.stop()
            self._busy_progress_running = False
        self.busy_progress.grid_remove()
        self.busy_percent_label.grid_remove()
        self.busy_percent.set("")
        self.parent.configure(cursor="")


__all__ = ["ProgressViewportMainWindow"]
