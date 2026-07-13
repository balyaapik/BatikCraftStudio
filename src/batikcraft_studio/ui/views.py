"""Workspace views for BatikCraft Studio."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.config import WorkspaceDefinition

from .layer_editor import LayerEditorWorkspaceView

StatusCallback = Callable[[str], None]
RefreshCallback = Callable[[], None]


class WorkspaceView(ttk.Frame):
    """Reusable informational view for workspaces not implemented yet."""

    def __init__(
        self,
        parent: tk.Misc,
        definition: WorkspaceDefinition,
        set_status: StatusCallback,
    ) -> None:
        super().__init__(parent, style="App.TFrame", padding=(34, 30))
        self.definition = definition
        self.set_status = set_status
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        _build_header(self, self.definition)

        body = ttk.Frame(self, style="App.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1, uniform="workspace-card")
        body.columnconfigure(1, weight=1, uniform="workspace-card")
        body.rowconfigure(0, weight=1)

        primary_title, primary_items = self._primary_card_content()
        secondary_title, secondary_items = self._secondary_card_content()
        _build_card(body, 0, primary_title, primary_items)
        _build_card(body, 1, secondary_title, secondary_items)

        actions = ttk.Frame(self, style="App.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(24, 0))
        ttk.Button(
            actions,
            text=self._action_label(),
            style="Primary.TButton",
            command=self._report_scoped_action,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Milestone details",
            style="Secondary.TButton",
            command=lambda: self.set_status(
                f"{self.definition.label}: scope is documented in README.md."
            ),
        ).pack(side="left", padx=(10, 0))

    def refresh_project(self) -> None:
        """Hook used by project-aware workspaces."""

    def _primary_card_content(self) -> tuple[str, tuple[str, ...]]:
        content: dict[str, tuple[str, tuple[str, ...]]] = {
            "dashboard": (
                "Layer editor ready",
                (
                    "Create, open, save, and close editable .batikcraft projects.",
                    "Import PNG/JPEG images as editable raster layers.",
                    "Use transform, visibility, lock, ordering, undo, and redo controls.",
                ),
            ),
            "batikification": (
                "Batikification workflow",
                (
                    "Import an object and create an editable object mask.",
                    "Choose a batik style and preservation strength.",
                    "Generate variations and insert one as a workspace layer.",
                ),
            ),
            "preview": (
                "Non-destructive repeat",
                (
                    "Preview repetitions without changing the source tile.",
                    "Support straight, mirror, half-drop, and half-brick modes.",
                    "Export a tile separately from the larger repeat preview.",
                ),
            ),
            "publish": (
                "Desktop responsibility",
                (
                    "Freeze and hash a specific design version.",
                    "Render protected previews and a publishing manifest.",
                    "Send assets to the website; keep bidding out of the desktop.",
                ),
            ),
        }
        return content[self.definition.key]

    def _secondary_card_content(self) -> tuple[str, tuple[str, ...]]:
        content: dict[str, tuple[str, tuple[str, ...]]] = {
            "dashboard": (
                "Development rules",
                (
                    "One milestone per branch and pull request.",
                    "Manual workflows remain usable when AI is unavailable.",
                    "UI, domain logic, imaging, and external APIs stay separated.",
                ),
            ),
            "batikification": (
                "Stable fallback first",
                (
                    "Procedural pattern fill is implemented before GAN inference.",
                    "Object outline and fill can be separated for editing.",
                    "The original object, mask, style, and seed remain recoverable.",
                ),
            ),
            "preview": (
                "Quality checks",
                (
                    "Detect visible seams at tile boundaries.",
                    "Allow zoomed inspection and multiple repeat densities.",
                    "Keep preview rendering outside permanent project mutations.",
                ),
            ),
            "publish": (
                "Website responsibility",
                (
                    "Public listing, bidder identity, bid validation, and timing.",
                    "Payment, winner confirmation, and downloadable licensed assets.",
                    "Audit trail for the selected design version and license terms.",
                ),
            ),
        }
        return content[self.definition.key]

    def _action_label(self) -> str:
        labels = {
            "dashboard": "Open Motif Editor",
            "batikification": "Prepare batikification milestone",
            "preview": "Prepare pattern milestone",
            "publish": "Prepare publishing milestone",
        }
        return labels[self.definition.key]

    def _report_scoped_action(self) -> None:
        self.set_status(
            f"{self.definition.label} is intentionally scoped for a later milestone."
        )


def create_workspace_view(
    parent: tk.Misc,
    *,
    definition: WorkspaceDefinition,
    set_status: StatusCallback,
    session: ProjectSession,
    refresh_context: RefreshCallback,
) -> WorkspaceView | LayerEditorWorkspaceView:
    if definition.key == "editor":
        return LayerEditorWorkspaceView(
            parent,
            definition=definition,
            set_status=set_status,
            session=session,
            refresh_context=refresh_context,
        )
    return WorkspaceView(parent, definition, set_status)


def _build_header(
    parent: ttk.Frame,
    definition: WorkspaceDefinition,
    *,
    compact: bool = False,
) -> None:
    header = ttk.Frame(parent, style="App.TFrame")
    header.grid(row=0, column=0, sticky="ew", pady=(0, 16 if compact else 24))
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text=definition.eyebrow, style="Eyebrow.TLabel").grid(
        row=0,
        column=0,
        sticky="w",
    )
    ttk.Label(header, text=definition.title, style="Title.TLabel").grid(
        row=1,
        column=0,
        sticky="w",
        pady=(5, 8),
    )
    ttk.Label(
        header,
        text=definition.description,
        style="Description.TLabel",
        wraplength=820,
        justify="left",
    ).grid(row=2, column=0, sticky="w")


def _build_card(
    parent: ttk.Frame,
    column: int,
    title: str,
    items: tuple[str, ...],
) -> None:
    card = ttk.Frame(parent, style="Surface.TFrame", padding=(22, 20))
    card.grid(
        row=0,
        column=column,
        sticky="nsew",
        padx=(0, 10) if column == 0 else (10, 0),
    )
    card.columnconfigure(0, weight=1)
    ttk.Label(card, text=title, style="CardTitle.TLabel").grid(
        row=0,
        column=0,
        sticky="w",
        pady=(0, 14),
    )
    for index, item in enumerate(items, start=1):
        row = ttk.Frame(card, style="Surface.TFrame")
        row.grid(row=index, column=0, sticky="ew", pady=5)
        ttk.Label(row, text="•", style="CardText.TLabel").pack(side="left", anchor="n")
        ttk.Label(
            row,
            text=item,
            style="CardText.TLabel",
            wraplength=390,
            justify="left",
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))
