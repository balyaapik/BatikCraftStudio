"""Dockable panels that can also be collected into a shared notebook tab area."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from .tool_icons import create_tool_icon
from .tooltip import ToolTip

PanelBuilder = Callable[[ttk.Frame], None]
StateCallback = Callable[[], None]


class TabbedDockablePanel:
    """Rebuild a panel between docked, floating, and shared-tab presentations."""

    def __init__(
        self,
        owner: tk.Misc,
        *,
        key: str,
        title: str,
        host: ttk.Frame,
        tab_host: ttk.Notebook,
        builder: PanelBuilder,
        on_state_change: StateCallback | None = None,
        floating_size: tuple[int, int] = (340, 520),
    ) -> None:
        self.owner = owner
        self.key = key
        self.title = title
        self.host = host
        self.tab_host = tab_host
        self.builder = builder
        self.on_state_change = on_state_change
        self.floating_size = floating_size
        self.mode = "dock"
        self._shell: ttk.Frame | None = None
        self._window: tk.Toplevel | None = None
        self._mount()

    @property
    def is_docked(self) -> bool:
        return self.mode == "dock"

    @property
    def is_tabbed(self) -> bool:
        return self.mode == "tab"

    def toggle(self) -> None:
        if self.mode == "float":
            self.dock()
        else:
            self.undock()

    def dock(self) -> None:
        self._set_mode("dock")

    def undock(self) -> None:
        if self.mode == "float":
            if self._window is not None:
                self._window.deiconify()
                self._window.lift()
            return
        self._set_mode("float")

    def tab(self) -> None:
        self._set_mode("tab")

    def close(self) -> None:
        self._destroy_shell()
        self._destroy_window()

    def _set_mode(self, mode: str) -> None:
        if mode not in {"dock", "float", "tab"}:
            raise ValueError(f"Unknown panel mode: {mode}")
        if self.mode == mode:
            if mode == "float" and self._window is not None:
                self._window.deiconify()
                self._window.lift()
            elif mode == "tab" and self._shell is not None:
                self.tab_host.select(self._shell)
            return
        self._destroy_shell()
        self._destroy_window()
        self.mode = mode
        self._mount()
        if self.on_state_change is not None:
            self.on_state_change()

    def _mount(self) -> None:
        if self.mode == "float":
            window = tk.Toplevel(self.owner.winfo_toplevel())
            self._window = window
            window.title(self.title)
            width, height = self.floating_size
            window.geometry(f"{width}x{height}")
            window.minsize(min(width, 240), min(height, 260))
            window.protocol("WM_DELETE_WINDOW", self.dock)
            parent: tk.Misc = window
        elif self.mode == "tab":
            parent = self.tab_host
        else:
            parent = self.host

        shell = ttk.Frame(parent, style="Dock.TFrame", padding=(6, 6))
        self._shell = shell
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)
        if self.mode == "float":
            shell.pack(fill="both", expand=True)
        elif self.mode == "tab":
            self.tab_host.add(shell, text=self.title)
            self.tab_host.select(shell)
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
        self._header_icon_button(
            header,
            "dock_restore",
            "Dock panel",
            self.dock,
            1,
            enabled=self.mode != "dock",
        )
        self._header_icon_button(
            header,
            "dock_tab",
            "Show panel as tab",
            self.tab,
            2,
            enabled=self.mode != "tab",
        )
        self._header_icon_button(
            header,
            "dock_float",
            "Float panel",
            self.undock,
            3,
            enabled=self.mode != "float",
        )

        content = ttk.Frame(shell, style="Dock.TFrame")
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        self.builder(content)
        if self.mode == "float" and self._window is not None:
            self._window.transient(self.owner.winfo_toplevel())
            self._window.lift()

    def _header_icon_button(
        self,
        parent: ttk.Frame,
        icon_name: str,
        tooltip: str,
        command: Callable[[], None],
        column: int,
        *,
        enabled: bool,
    ) -> None:
        image = create_tool_icon(parent, icon_name, size=15)
        button = ttk.Button(
            parent,
            image=image,
            command=command,
            style="Secondary.TButton",
            state=tk.NORMAL if enabled else tk.DISABLED,
            takefocus=True,
        )
        button.image = image  # type: ignore[attr-defined]
        button.grid(row=0, column=column, sticky="e", padx=(3, 0))
        ToolTip(button, tooltip)

    def _destroy_shell(self) -> None:
        if self._shell is not None and self._shell.winfo_exists():
            self._shell.destroy()
        self._shell = None

    def _destroy_window(self) -> None:
        if self._window is not None and self._window.winfo_exists():
            self._window.destroy()
        self._window = None


__all__ = ["TabbedDockablePanel"]
