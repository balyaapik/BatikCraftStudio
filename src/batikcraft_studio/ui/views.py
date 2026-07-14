"""Workspace views for BatikCraft Studio."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.config import WorkspaceDefinition

from .icons import create_icon
from .paint_layer_editor import PaintLayerEditorWorkspaceView
from .theme import COLORS

StatusCallback = Callable[[str], None]
RefreshCallback = Callable[[], None]


class WorkspaceView(ttk.Frame):
    """Compact native placeholder for workspaces that are not implemented yet."""

    def __init__(
        self,
        parent: tk.Misc,
        definition: WorkspaceDefinition,
        set_status: StatusCallback,
    ) -> None:
        super().__init__(parent, style="App.TFrame")
        self.definition = definition
        self.set_status = set_status
        self._icon = create_icon(self, definition.key, size=42, color=COLORS["muted_ink"])
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        titlebar = ttk.Frame(self, style="Toolbar.TFrame", padding=(8, 4))
        titlebar.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            titlebar,
            text=self.definition.label,
            style="ProjectTitle.TLabel",
        ).pack(side="left")

        workspace = ttk.Frame(self, style="App.TFrame")
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(0, weight=1)

        empty = ttk.Frame(workspace, style="Surface.TFrame", padding=(24, 20))
        empty.grid(row=0, column=0)
        ttk.Label(empty, image=self._icon, style="Muted.TLabel").pack(pady=(0, 10))
        ttk.Label(
            empty,
            text=self.definition.title,
            style="PanelTitle.TLabel",
            anchor="center",
        ).pack()
        ttk.Label(
            empty,
            text=self.definition.description,
            style="Muted.TLabel",
            wraplength=460,
            justify="center",
        ).pack(pady=(4, 0))

    def refresh_project(self) -> None:
        """Hook used by project-aware workspaces."""


def create_workspace_view(
    parent: tk.Misc,
    *,
    definition: WorkspaceDefinition,
    set_status: StatusCallback,
    session: ProjectSession,
    refresh_context: RefreshCallback,
) -> WorkspaceView | PaintLayerEditorWorkspaceView:
    if definition.key == "editor":
        return PaintLayerEditorWorkspaceView(
            parent,
            definition=definition,
            set_status=set_status,
            session=session,
            refresh_context=refresh_context,
        )
    return WorkspaceView(parent, definition, set_status)
