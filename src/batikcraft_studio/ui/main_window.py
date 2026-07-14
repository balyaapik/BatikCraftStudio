"""Single-workspace bilingual shell for the asset-first BatikCraft editor."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from tkinter import ttk

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.config import APP_NAME, get_workspace
from batikcraft_studio.i18n import tr

from .compact_asset_editor import CompactAssetEditorWorkspaceView
from .theme import COLORS
from .views import create_workspace_view
from .widgets import icon_button

Command = Callable[[], object]


class MainWindow(ttk.Frame):
    """Top-level shell with one editor, compact toolbar, and status bar."""

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
        self.active_view: CompactAssetEditorWorkspaceView | None = None
        self.status_text = tk.StringVar(value=tr("status.ready"))
        self.project_title_text = tk.StringVar(value=tr("status.no_project"))
        self.project_meta_text = tk.StringVar(value=tr("status.create_or_open"))
        self.project_path_text = tk.StringVar(value="")

        self._build_layout()
        self.show_workspace("editor")
        self.refresh_project_context()

    def _build_layout(self) -> None:
        self.pack(fill="both", expand=True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_command_toolbar()

        self.workspace_host = ttk.Frame(self, style="App.TFrame")
        self.workspace_host.grid(row=1, column=0, sticky="nsew")
        self.workspace_host.columnconfigure(0, weight=1)
        self.workspace_host.rowconfigure(0, weight=1)

        ttk.Label(self, textvariable=self.status_text, style="Status.TLabel").grid(
            row=2,
            column=0,
            sticky="ew",
        )

    def _build_command_toolbar(self) -> None:
        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(4, 3))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(4, weight=1)

        actions = ttk.Frame(toolbar, style="Toolbar.TFrame")
        actions.grid(row=0, column=0, sticky="w")
        for icon, tooltip_key, command in (
            ("new", "toolbar.new", self.file_commands.get("new")),
            ("open", "toolbar.open", self.file_commands.get("open")),
            ("save", "toolbar.save", self.file_commands.get("save")),
        ):
            if command is not None:
                icon_button(
                    actions,
                    icon=icon,
                    tooltip=tr(tooltip_key),
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
        for icon, tooltip_key, command in (
            ("import", "toolbar.import", self.editor_import_image),
            ("undo", "toolbar.undo", self.editor_undo),
            ("redo", "toolbar.redo", self.editor_redo),
            ("duplicate", "toolbar.duplicate", self.editor_duplicate),
            ("delete", "toolbar.delete", self.editor_delete),
        ):
            icon_button(
                edit_actions,
                icon=icon,
                tooltip=tr(tooltip_key),
                command=command,
            ).pack(side="left", padx=1)

        ttk.Separator(toolbar, orient=tk.VERTICAL).grid(
            row=0,
            column=3,
            sticky="ns",
            padx=5,
        )
        library_actions = ttk.Frame(toolbar, style="Toolbar.TFrame")
        library_actions.grid(row=0, column=4, sticky="w")
        icon_button(
            library_actions,
            icon="batikification",
            tooltip=tr("toolbar.library"),
            command=self.focus_asset_library,
        ).pack(side="left", padx=1)

        project = ttk.Frame(toolbar, style="Toolbar.TFrame")
        project.grid(row=0, column=5, sticky="ew", padx=(12, 6))
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

    def show_workspace(self, _key: str = "editor") -> None:
        """Open the only active editor workspace and retain compatibility callers."""

        if self.active_view is None or not self.active_view.winfo_exists():
            definition = get_workspace("editor")
            self.active_view = create_workspace_view(
                self.workspace_host,
                definition=definition,
                set_status=self.set_status,
                session=self.session,
                refresh_context=self.refresh_project_context,
            )
            self.active_view.grid(row=0, column=0, sticky="nsew")
        self.active_workspace_key = "editor"
        self._update_window_title()
        self.set_status(tr("status.editor"))

    def refresh_project_context(self) -> None:
        """Refresh compact project information and editor content."""

        snapshot = self.session.snapshot()
        if not snapshot.has_project:
            self.project_title_text.set(tr("status.no_project"))
            self.project_meta_text.set(tr("status.create_or_open"))
            self.project_path_text.set("")
        else:
            dirty = " *" if snapshot.dirty else ""
            self.project_title_text.set(f"{snapshot.title}{dirty}")
            object_count = self.session.require_project().object_count
            self.project_meta_text.set(
                tr(
                    "status.layers_objects",
                    width=snapshot.width,
                    height=snapshot.height,
                    layers=snapshot.layer_count,
                    objects=object_count,
                )
            )
            path = snapshot.display_path
            self.project_path_text.set(path if len(path) <= 48 else f"…{path[-47:]}")

        if self.active_view is not None:
            self.active_view.refresh_project()
        self._update_window_title()

    def editor_import_image(self) -> None:
        self._editor().import_asset_dialog()

    def editor_undo(self) -> None:
        self._editor().undo()

    def editor_redo(self) -> None:
        self._editor().redo()

    def editor_duplicate(self) -> None:
        self._editor().duplicate_active()

    def editor_delete(self) -> None:
        self._editor().delete_active()

    def focus_asset_library(self) -> None:
        self._editor().focus_asset_library()

    def install_asset_pack(self) -> None:
        self._editor().install_asset_pack_dialog()

    def uninstall_asset_pack(self) -> None:
        self._editor().uninstall_selected_pack()

    def export_selected_asset(self) -> None:
        self._editor().export_asset_dialog()

    def open_brush_settings(self) -> None:
        self._editor().open_brush_settings()

    def open_eraser_settings(self) -> None:
        self._editor().open_eraser_settings()

    def open_shape_settings(self, shape_type: str) -> None:
        self._editor().open_shape_settings(shape_type)

    def open_motif_settings(self) -> None:
        self._editor().open_motif_settings()

    def open_isen_settings(self) -> None:
        self._editor().open_isen_settings()

    def open_transform_settings(self) -> None:
        self._editor().open_transform_settings()

    def open_asset_metadata_settings(self) -> None:
        self._editor().open_asset_metadata_settings()

    def open_humanize_settings(self) -> None:
        self._editor().open_humanize_settings()

    def reset_humanize(self) -> None:
        self._editor().reset_humanize()

    def activate_select_tool(self) -> None:
        self._editor().activate_select_tool()

    def new_folder(self) -> None:
        self._editor().new_folder()

    def new_object_layer(self) -> None:
        self._editor().new_object_layer()

    def new_paint_layer(self) -> None:
        self._editor().new_paint_layer()

    def toggle_visibility(self) -> None:
        self._editor().toggle_visibility()

    def toggle_lock(self) -> None:
        self._editor().toggle_lock()

    def _editor(self) -> CompactAssetEditorWorkspaceView:
        self.show_workspace("editor")
        if self.active_view is None:
            raise RuntimeError("Motif Editor could not be opened.")
        return self.active_view

    def set_status(self, message: str) -> None:
        self.status_text.set(message)

    def flash_status(self, message: str, duration_ms: int = 3500) -> None:
        self.set_status(message)
        self.after(duration_ms, lambda: self.set_status(tr("status.ready")))

    def focus_navigation(self) -> None:
        self.focus_asset_library()

    def set_busy(self, busy: bool, message: str | None = None) -> None:
        self.parent.configure(cursor="watch" if busy else "")
        if message:
            self.set_status(message)
        elif not busy:
            self.set_status(tr("status.ready"))
        self.parent.update_idletasks()

    def _update_window_title(self) -> None:
        snapshot = self.session.snapshot()
        if snapshot.has_project:
            dirty = " *" if snapshot.dirty else ""
            self.parent.title(f"{snapshot.title}{dirty} — {APP_NAME}")
        else:
            self.parent.title(APP_NAME)

    @property
    def background_color(self) -> str:
        return COLORS["canvas"]
