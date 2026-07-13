"""Native hover tooltips for compact icon-only controls."""

from __future__ import annotations

import tkinter as tk


class ToolTip:
    """Show a small transient label when the pointer rests over a widget."""

    def __init__(self, widget: tk.Misc, text: str, *, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: str | None = None
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._window is not None or not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 8
        y = self.widget.winfo_rooty() + 4
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            window,
            text=self.text,
            background="#2F2F2F",
            foreground="#FFFFFF",
            relief="solid",
            borderwidth=1,
            padx=7,
            pady=4,
            font=("Segoe UI", 9),
        )
        label.pack()
        self._window = window

    def _hide(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        self._cancel()
        if self._window is not None:
            self._window.destroy()
            self._window = None
