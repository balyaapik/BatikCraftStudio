"""Main application frame and compact native workspace navigation."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from tkinter import ttk

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.config import APP_NAME, WORKSPACES, get_workspace

from .layer_editor import LayerEditorWorkspaceView
from .theme import COLORS
from .views import WorkspaceView, create_workspace_view
from .widgets import icon_button

Command = Callable[[], object]


class MainWindow(ttk.Frame):
    """Top-level editor shell with icon toolbars, rail navigation, and status bar."""

    def __init__(
        self,
        parent: tk.Tk,
        session: ProjectSession,
        *,
        file_commands: Mapping[str, Command] | None = None,
    ) -> None:
        super().__init__(parent, style="App.TFrame")
        self.parent = parent
        self.session = session
        self.file_commands = dict(file_commands or {})
        self.active_workspace_key = "editor"
        self.active_view: WorkspaceView | LayerEditorWorkspaceView | None = None
        self.nav_buttons: dict[str, ttk.Button] = {}
        self.status_text = tk.StringVar(value="Ready")
        self.project_title_text = tk.StringVar(value="No project")
        self.project_meta_text = tk.StringVar(value="Create or open a .batikcraft project")
        self.project_path_text = tk.StringVar(value="")

        self._build_layout()
        self._bind_shortcuts()
        self.show_workspace(self.active_workspace_key)
        self.refresh_project_context()

    def _build_layout(self) -> None:
        self.pack(fill="both", expand=True)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_command_toolbar()
        self._build_workspace_rail()

        self.workspace_host = ttk.Frame(self, style="App.TFrame")
        self.workspace_host.grid(row=1, column=1, sticky="nsew")
        self.workspace_host.columnconfigure(0, weight=1)
        self.workspace_host.rowconfigure(0, weight=1)

        status = ttk.Label(self, textvariable=self.status_text, style="Status.TLabel")
        status.grid(row=2, column=0, columnspan=2, sticky="ew")

    def _build_command_toolbar(self) -> None:
        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(4, 3))
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        toolbar.columnconfigure(3, weight=1)

        actions = ttk.Frame(toolbar, style="Toolbar.TFrame")
        actions.grid(row=0, column=0, sticky="w")
        file_buttons = (
            ("new", "New project (Ctrl+N)", self.file_commands.get("new")),
            ("open", "Open project (Ctrl+O)", self.file_commands.get("open")),
            ("save", "Save project (Ctrl+S)", self.file_commands.get("save")),
        )
        for icon, tooltip, command in file_buttons:
            if command is not None:
                icon_button(
                    actions,
                    icon=icon,
                    tooltip=tooltip,
                    command=command,
                ).pack(side="left", padx=1)

        ttk.Separator(toolbar, orient=tk.VERTICAL).grid(
            row=0,
            column=1,
            sticky="ns",
            padx=5,
        )
        edit_actions = ttk.Frame(toolbar, style="Toolbar.TFrame")
        edit_actions.grid(row=0, column=2, sticky="w")
        for icon, tooltip, command in (
            ("import", "Import image (Ctrl+I)", self.editor_import_image),
            ("undo", "Undo (Ctrl+Z)", self.editor_undo),
            ("redo", "Redo (Ctrl+Y)", self.editor_redo),
            ("duplicate", "Duplicate layer (Ctrl+D)", self.editor_duplicate),
            ("delete", "Delete selected layer", self.editor_delete),
        ):
            icon_button(
                edit_actions,
                icon=icon,
                tooltip=tooltip,
                command=command,
            ).pack(side="left", padx=1)

        project = ttk.Frame(toolbar, style="Toolbar.TFrame")
        project.grid(row=0, column=3, sticky="ew", padx=(12, 6))
        project.columnconfigure(0, weight=1)
        ttk.Label(
            project,
            textvariable=self.project_title_text,
            style="ProjectTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            project,
            textvariable=self.project_meta_text,
            style="ProjectMeta.TLabel",
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))
        ttk.Label(
            project,
            textvariable=self.project_path_text,
            style="ProjectPath.TLabel",
        ).grid(row=0, column=2, sticky="e", padx=(12, 0))

    def _build_workspace_rail(self) -> None:
        rail = ttk.Frame(self, style="Rail.TFrame", width=46)
        rail.grid(row=1, column=0, sticky="nsw")
        rail.grid_propagate(False)
        rail.columnconfigure(0, weight=1)

        for index, workspace in enumerate(WORKSPACES):
            button = icon_button(
                rail,
                icon=workspace.key,
                tooltip=f"{workspace.label} (Ctrl+{index + 1})",
                command=lambda key=workspace.key: self.show_workspace(key),
                style="Rail.TButton",
                size=21,
            )
            button.grid(row=index, column=0, sticky="ew", pady=(3 if index == 0 else 1, 1))
            self.nav_buttons[workspace.key] = button

    def _bind_shortcuts(self) -> None:
        for index, workspace in enumerate(WORKSPACES, start=1):
            self.parent.bind_all(
                f"<Control-Key-{index}>",
                lambda _event, key=workspace.key: self.show_workspace(key),
            )

    def show_workspace(self, key: str) -> None:
        """Replace the center workspace and update the active rail icon."""

        definition = get_workspace(key)
        self.active_workspace_key = key
        if self.active_view is not None:
            self.active_view.destroy()

        self.active_view = create_workspace_view(
            self.workspace_host,
            definition=definition,
            set_status=self.set_status,
            session=self.session,
            refresh_context=self.refresh_project_context,
        )
        self.active_view.grid(row=0, column=0, sticky="nsew")

        for workspace_key, button in self.nav_buttons.items():
            button.configure(
                style="RailActive.TButton" if workspace_key == key else "Rail.TButton"
            )
        self._update_window_title()
        self.set_status(definition.label)

    def refresh_project_context(self) -> None:
        """Refresh compact project information and the active workspace."""

        snapshot = self.session.snapshot()
        if not snapshot.has_project:
            self.project_title_text.set("No project")
            self.project_meta_text.set("Create or open a .batikcraft project")
            self.project_path_text.set("")
        else:
            dirty = " *" if snapshot.dirty else ""
            self.project_title_text.set(f"{snapshot.title}{dirty}")
            self.project_meta_text.set(
                f"{snapshot.width} × {snapshot.height}px  |  {snapshot.layer_count} layers"
            )
            path = snapshot.display_path
            self.project_path_text.set(path if len(path) <= 48 else f"…{path[-47:]}")

        if self.active_view is not None:
            self.active_view.refresh_project()
        self._update_window_title()

    def editor_import_image(self) -> None:
        self._require_editor_view().import_image_dialog()

    def editor_undo(self) -> None:
        self._require_editor_view().undo()

    def editor_redo(self) -> None:
        self._require_editor_view().redo()

    def editor_duplicate(self) -> None:
        self._require_editor_view().duplicate_active()

    def editor_delete(self) -> None:
        self._require_editor_view().delete_active()

    def _require_editor_view(self) -> LayerEditorWorkspaceView:
        if not isinstance(self.active_view, LayerEditorWorkspaceView):
            self.show_workspace("editor")
        if not isinstance(self.active_view, LayerEditorWorkspaceView):
            raise RuntimeError("Motif Editor could not be opened.")
        return self.active_view

    def set_status(self, message: str) -> None:
        self.status_text.set(message)

    def flash_status(self, message: str, duration_ms: int = 3500) -> None:
        self.set_status(message)
        self.after(
            duration_ms,
            lambda: self.set_status(get_workspace(self.active_workspace_key).label),
        )

    def focus_navigation(self) -> None:
        self.nav_buttons[self.active_workspace_key].focus_set()

    def set_busy(self, busy: bool, message: str | None = None) -> None:
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
            self.parent.title(f"{snapshot.title}{dirty} — {workspace} — {APP_NAME}")
        else:
            self.parent.title(f"{APP_NAME} — {workspace}")

    @property
    def background_color(self) -> str:
        return COLORS["canvas"]
