"""Main application frame and workspace navigation."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from batikcraft_studio.config import APP_NAME, APP_VERSION, WORKSPACES, get_workspace

from .theme import COLORS
from .views import WorkspaceView


class MainWindow(ttk.Frame):
    """Top-level application layout shared by all feature workspaces."""

    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent, style="App.TFrame")
        self.parent = parent
        self.active_workspace_key = "dashboard"
        self.active_view: WorkspaceView | None = None
        self.nav_buttons: dict[str, ttk.Button] = {}
        self.status_text = tk.StringVar(value="Ready — application foundation loaded.")

        self._build_layout()
        self._bind_shortcuts()
        self.show_workspace(self.active_workspace_key)

    def _build_layout(self) -> None:
        self.pack(fill="both", expand=True)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(self, style="Sidebar.TFrame", width=244)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(2, weight=1)

        brand = ttk.Frame(sidebar, style="Sidebar.TFrame", padding=(20, 22, 18, 18))
        brand.grid(row=0, column=0, sticky="ew")
        ttk.Label(brand, text=APP_NAME, style="Brand.TLabel").pack(anchor="w")
        ttk.Label(
            brand,
            text=f"Native motif workspace  •  v{APP_VERSION}",
            style="BrandMeta.TLabel",
        ).pack(anchor="w", pady=(5, 0))

        separator = tk.Frame(sidebar, height=1, background="#4D4540")
        separator.grid(row=1, column=0, sticky="ew", padx=18)

        navigation = ttk.Frame(sidebar, style="Sidebar.TFrame", padding=(12, 18))
        navigation.grid(row=2, column=0, sticky="nsew")
        navigation.columnconfigure(0, weight=1)

        for index, workspace in enumerate(WORKSPACES):
            button = ttk.Button(
                navigation,
                text=workspace.label,
                style="Nav.TButton",
                command=lambda key=workspace.key: self.show_workspace(key),
            )
            button.grid(row=index, column=0, sticky="ew", pady=2)
            self.nav_buttons[workspace.key] = button

        footer = ttk.Frame(sidebar, style="Sidebar.TFrame", padding=(20, 16))
        footer.grid(row=3, column=0, sticky="ew")
        ttk.Label(
            footer,
            text="Built incrementally for IBM Bob",
            style="BrandMeta.TLabel",
            wraplength=190,
            justify="left",
        ).pack(anchor="w")

        content_shell = ttk.Frame(self, style="App.TFrame")
        content_shell.grid(row=0, column=1, sticky="nsew")
        content_shell.columnconfigure(0, weight=1)
        content_shell.rowconfigure(0, weight=1)

        self.workspace_host = ttk.Frame(content_shell, style="App.TFrame")
        self.workspace_host.grid(row=0, column=0, sticky="nsew")
        self.workspace_host.columnconfigure(0, weight=1)
        self.workspace_host.rowconfigure(0, weight=1)

        status = ttk.Label(content_shell, textvariable=self.status_text, style="Status.TLabel")
        status.grid(row=1, column=0, sticky="ew")

    def _bind_shortcuts(self) -> None:
        for index, workspace in enumerate(WORKSPACES, start=1):
            self.parent.bind_all(
                f"<Control-Key-{index}>",
                lambda _event, key=workspace.key: self.show_workspace(key),
            )

    def show_workspace(self, key: str) -> None:
        """Replace the current workspace and update navigation state."""

        definition = get_workspace(key)
        self.active_workspace_key = key

        if self.active_view is not None:
            self.active_view.destroy()

        self.active_view = WorkspaceView(
            self.workspace_host,
            definition=definition,
            set_status=self.set_status,
        )
        self.active_view.grid(row=0, column=0, sticky="nsew")

        for workspace_key, button in self.nav_buttons.items():
            button.configure(
                style="NavActive.TButton" if workspace_key == key else "Nav.TButton"
            )

        self.parent.title(f"{APP_NAME} — {definition.label}")
        self.set_status(f"Workspace opened: {definition.label}")

    def set_status(self, message: str) -> None:
        """Expose a single status channel for all child workspaces."""

        self.status_text.set(message)

    def flash_status(self, message: str, duration_ms: int = 3500) -> None:
        """Show a temporary status and restore the active workspace message."""

        self.set_status(message)
        self.after(
            duration_ms,
            lambda: self.set_status(
                f"Workspace active: {get_workspace(self.active_workspace_key).label}"
            ),
        )

    def focus_navigation(self) -> None:
        """Move keyboard focus to the active navigation button."""

        self.nav_buttons[self.active_workspace_key].focus_set()

    def set_busy(self, busy: bool, message: str | None = None) -> None:
        """Foundation hook for future file and AI background operations."""

        self.parent.configure(cursor="watch" if busy else "")
        if message:
            self.set_status(message)
        elif not busy:
            self.set_status("Ready")

        # Force cursor updates without processing unrelated queued actions.
        self.parent.update_idletasks()

    @property
    def background_color(self) -> str:
        """Expose the canvas color for future classic Tk widgets."""

        return COLORS["canvas"]
