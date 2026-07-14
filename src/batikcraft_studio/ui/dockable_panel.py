"""Reusable dock/undock controller for Tkinter editor panels."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from batikcraft_studio.workspace_translations import install_workspace_translations

install_workspace_translations()

PanelBuilder = Callable[[ttk.Frame], None]
StateCallback = Callable[[], None]


class DockablePanel:
    """Rebuild one panel safely between a dock host and a floating window.

    Tk widgets cannot be reparented after creation. This controller therefore destroys
    and rebuilds only the presentation widgets while retaining editor variables and
    project/session state in the owning workspace.
    """

    def __init__(
        self,
        owner: tk.Misc,
        *,
        key: str,
        title: str,
        host: ttk.Frame,
        builder: PanelBuilder,
        on_state_change: StateCallback | None = None,
        floating_size: tuple[int, int] = (340, 520),
    ) -> None:
        self.owner = owner
        self.key = key
        self.title = title
        self.host = host
        self.builder = builder
        self.on_state_change = on_state_change
        self.floating_size = floating_size
        self.is_docked = True
        self._shell: ttk.Frame | None = None
        self._window: tk.Toplevel | None = None
        self._mount(self.host, floating=False)

    def toggle(self) -> None:
        """Toggle between the dock host and a floating utility window."""

        if self.is_docked:
            self.undock()
        else:
            self.dock()

    def undock(self) -> None:
        """Move the panel into a floating utility window by rebuilding its UI."""

        if not self.is_docked:
            if self._window is not None:
                self._window.deiconify()
                self._window.lift()
            return
        self._destroy_shell()
        self.is_docked = False
        if self.on_state_change is not None:
            self.on_state_change()

        window = tk.Toplevel(self.owner.winfo_toplevel())
        self._window = window
        window.title(self.title)
        width, height = self.floating_size
        window.geometry(f"{width}x{height}")
        window.minsize(min(width, 240), min(height, 260))
        window.protocol("WM_DELETE_WINDOW", self.dock)
        self._mount(window, floating=True)
        window.transient(self.owner.winfo_toplevel())
        window.lift()

    def dock(self) -> None:
        """Return a floating panel to its original dock host."""

        if self.is_docked:
            return
        self._destroy_shell()
        if self._window is not None:
            self._window.destroy()
            self._window = None
        self.is_docked = True
        if self.on_state_change is not None:
            self.on_state_change()
        self._mount(self.host, floating=False)

    def close(self) -> None:
        """Destroy both docked and floating presentation widgets."""

        self._destroy_shell()
        if self._window is not None:
            self._window.destroy()
            self._window = None

    def _mount(self, parent: tk.Misc, *, floating: bool) -> None:
        shell = ttk.Frame(parent, style="Dock.TFrame", padding=(6, 6))
        self._shell = shell
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)
        if floating:
            shell.pack(fill="both", expand=True)
        else:
            shell.grid(row=0, column=0, sticky="nsew")

        header = ttk.Frame(shell, style="Toolbar.TFrame", padding=(4, 3))
        header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=self.title, style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Button(
            header,
            text="⇲" if floating else "↗",
            width=3,
            style="Secondary.TButton",
            command=self.toggle,
        ).grid(row=0, column=1, sticky="e")

        content = ttk.Frame(shell, style="Dock.TFrame")
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        self.builder(content)

    def _destroy_shell(self) -> None:
        if self._shell is not None and self._shell.winfo_exists():
            self._shell.destroy()
        self._shell = None


__all__ = ["DockablePanel"]
