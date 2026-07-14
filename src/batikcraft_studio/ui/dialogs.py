"""Small modal dialogs used by the workspace shell."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import colorchooser, messagebox, simpledialog, ttk

from batikcraft_studio.domain import CanvasSpec, ProjectMetadata, ProjectValidationError
from batikcraft_studio.i18n import tr


@dataclass(frozen=True, slots=True)
class NewProjectRequest:
    title: str
    creator: str
    width: int
    height: int
    background_color: str


class NewProjectDialog(simpledialog.Dialog):
    """Collect the minimum metadata required to create a blank motif project."""

    def __init__(self, parent: tk.Misc) -> None:
        self.result: NewProjectRequest | None = None
        self.title_var = tk.StringVar()
        self.creator_var = tk.StringVar()
        self.width_var = tk.StringVar(value="2048")
        self.height_var = tk.StringVar(value="2048")
        self.background_var = tk.StringVar(value="#F4E9D8")
        super().__init__(parent, title=tr("dialog.new_project.title"))

    def body(self, master: tk.Misc) -> tk.Widget:
        form = ttk.Frame(master, padding=(8, 8))
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)

        fields = (
            (tr("dialog.new_project.project_title"), self.title_var),
            (tr("dialog.new_project.creator"), self.creator_var),
            (tr("dialog.new_project.canvas_width"), self.width_var),
            (tr("dialog.new_project.canvas_height"), self.height_var),
        )
        first_entry: ttk.Entry | None = None
        for row, (label, variable) in enumerate(fields):
            ttk.Label(form, text=label).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 14),
                pady=6,
            )
            entry = ttk.Entry(form, textvariable=variable, width=38)
            entry.grid(row=row, column=1, sticky="ew", pady=6)
            if first_entry is None:
                first_entry = entry

        ttk.Label(form, text=tr("dialog.new_project.background")).grid(
            row=4,
            column=0,
            sticky="w",
            padx=(0, 14),
            pady=6,
        )
        background_row = ttk.Frame(form)
        background_row.grid(row=4, column=1, sticky="ew", pady=6)
        background_row.columnconfigure(0, weight=1)
        ttk.Entry(background_row, textvariable=self.background_var).grid(
            row=0,
            column=0,
            sticky="ew",
        )
        ttk.Button(
            background_row,
            text=tr("common.choose"),
            command=self._choose_color,
        ).grid(row=0, column=1, padx=(8, 0))
        return first_entry or form

    def buttonbox(self) -> None:
        box = ttk.Frame(self)
        ttk.Button(
            box,
            text=tr("common.ok"),
            width=10,
            command=self.ok,
            default=tk.ACTIVE,
        ).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(
            box,
            text=tr("common.cancel"),
            width=10,
            command=self.cancel,
        ).pack(side=tk.LEFT, padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()

    def validate(self) -> bool:
        try:
            width = int(self.width_var.get().strip())
            height = int(self.height_var.get().strip())
            metadata = ProjectMetadata(
                title=self.title_var.get(),
                creator=self.creator_var.get(),
            )
            canvas = CanvasSpec(
                width=width,
                height=height,
                background_color=self.background_var.get().strip(),
            )
        except ValueError:
            messagebox.showerror(
                tr("dialog.invalid_canvas.title"),
                tr("dialog.invalid_canvas.message"),
                parent=self,
            )
            return False
        except ProjectValidationError as exc:
            messagebox.showerror(
                tr("dialog.invalid_project.title"),
                str(exc),
                parent=self,
            )
            return False

        self.result = NewProjectRequest(
            title=metadata.title,
            creator=metadata.creator,
            width=canvas.width,
            height=canvas.height,
            background_color=canvas.background_color,
        )
        return True

    def apply(self) -> None:
        return None

    def _choose_color(self) -> None:
        _rgb, color = colorchooser.askcolor(
            color=self.background_var.get(),
            parent=self,
            title=tr("dialog.new_project.choose_background"),
        )
        if color:
            self.background_var.set(color.upper())
