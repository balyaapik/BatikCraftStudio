"""Workspace view factory for the asset-first BatikCraft editor."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.config import WorkspaceDefinition

from .context_tool_editor_hotfix_v9 import ContextToolEditorWorkspaceView
from .icons import create_icon
from .theme import COLORS

StatusCallback = Callable[[str], None]
RefreshCallback = Callable[[], None]


class WorkspaceView(ttk.Frame):
    """Small placeholder retained only for backward-compatible workspace calls."""

    def __init__(
        self,
        parent: tk.Misc,
        definition: WorkspaceDefinition,
        set_status: StatusCallback,
    ) -> None:
        super().__init__(parent, style="App.TFrame")
        self.definition = definition
        self.set_status = set_status
        self._icon = create_icon(
            self,
            definition.key,
            size=42,
            color=COLORS["muted_ink"],
        )
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        empty = ttk.Frame(self, style="Surface.TFrame", padding=(24, 20))
        empty.grid(row=0, column=0)
        ttk.Label(empty, image=self._icon, style="Muted.TLabel").pack(pady=(0, 10))
        ttk.Label(
            empty,
            text=definition.title,
            style="PanelTitle.TLabel",
            anchor="center",
        ).pack()
        ttk.Label(
            empty,
            text="Fungsi ini belum aktif pada workflow asset-first.",
            style="Muted.TLabel",
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
) -> ContextToolEditorWorkspaceView:
    """Return the editor with recolor, AI backgrounds, and previous hotfixes."""

    return ContextToolEditorWorkspaceView(
        parent,
        definition=definition,
        set_status=set_status,
        session=session,
        refresh_context=refresh_context,
    )
