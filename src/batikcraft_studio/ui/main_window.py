"""Main application frame and workspace navigation."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.config import APP_NAME, APP_VERSION, WORKSPACES, get_workspace

from .theme import COLORS
from .views import EditorWorkspaceView, WorkspaceView, create_workspace_view


class MainWindow(ttk.Frame):
    """Top-level application layout shared by all feature workspaces."""

    def __init__(self, parent: tk.Tk, session: ProjectSession) -> None:
        super().__init__(parent, style="App.TFrame")
        self.parent = parent
        self.session = session
        self.active_workspace_key = "dashboard"
        self.active_view: WorkspaceView | EditorWorkspaceView | None = None
        self.nav_buttons: dict[str, ttk.Button] = {}
        self.status_text = tk.StringVar(value="Ready — workspace shell loaded.")
        self.project_title_text = tk.StringVar(value="No project open")
        self.project_meta_text = tk.StringVar(value="Create or open a .batikcraft project")
        self.project_path_text = tk.StringVar(value="")

        self._build_layout()
        self._bind_shortcuts()
        self.show_workspace(self.active_workspace_key)
        self.refresh_project_context()

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
        content_shell.rowconfigure(1, weight=1)

        project_bar = ttk.Frame(content_shell, style="Surface.TFrame", padding=(20, 12))
        project_bar.grid(row=0, column=0, sticky="ew")
        project_bar.columnconfigure(0, weight=1)
        ttk.Label(
            project_bar,
            textvariable=self.project_title_text,
            style="ProjectTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            project_bar,
            textvariable=self.project_meta_text,
            style="ProjectMeta.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Label(
            project_bar,
            textvariable=self.project_path_text,
            style="ProjectPath.TLabel",
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(20, 0))

        self.workspace_host = ttk.Frame(content_shell, style="App.TFrame")
        self.workspace_host.grid(row=1, column=0, sticky="nsew")
        self.workspace_host.columnconfigure(0, weight=1)
        self.workspace_host.rowconfigure(0, weight=1)

        status = ttk.Label(content_shell, textvariable=self.status_text, style="Status.TLabel")
        status.grid(row=2, column=0, sticky="ew")

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

        self.active_view = create_workspace_view(
            self.workspace_host,
            definition=definition,
            set_status=self.set_status,
            session=self.session,
        )
        self.active_view.grid(row=0, column=0, sticky="nsew")

        for workspace_key, button in self.nav_buttons.items():
            button.configure(
                style="NavActive.TButton" if workspace_key == key else "Nav.TButton"
            )

        self._update_window_title()
        self.set_status(f"Workspace opened: {definition.label}")

    def refresh_project_context(self) -> None:
        """Refresh project labels and the active workspace after session changes."""

        snapshot = self.session.snapshot()
        if not snapshot.has_project:
            self.project_title_text.set("No project open")
            self.project_meta_text.set("Create or open a .batikcraft project")
            self.project_path_text.set("")
        else:
            dirty_label = "Unsaved changes" if snapshot.dirty else "Saved"
            self.project_title_text.set(f"{snapshot.title}  •  {dirty_label}")
            self.project_meta_text.set(
                f"Creator: {snapshot.creator}  •  "
                f"Canvas: {snapshot.width} × {snapshot.height}px  •  "
                f"Layers: {snapshot.layer_count}"
            )
            self.project_path_text.set(snapshot.display_path)

        if self.active_view is not None:
            self.active_view.refresh_project()
        self._update_window_title()

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
        self.parent.update_idletasks()

    def _update_window_title(self) -> None:
        workspace = get_workspace(self.active_workspace_key).label
        snapshot = self.session.snapshot()
        if snapshot.has_project:
            dirty = " *" if snapshot.dirty else ""
            project_label = f"{snapshot.title}{dirty}"
            self.parent.title(f"{project_label} — {workspace} — {APP_NAME}")
        else:
            self.parent.title(f"{APP_NAME} — {workspace}")

    @property
    def background_color(self) -> str:
        """Expose the canvas color for classic Tk widgets."""

        return COLORS["canvas"]
