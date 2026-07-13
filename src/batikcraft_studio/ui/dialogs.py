"""Small modal dialogs used by the workspace shell."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import colorchooser, messagebox, simpledialog, ttk

from batikcraft_studio.domain import CanvasSpec, ProjectMetadata, ProjectValidationError


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
        super().__init__(parent, title="New BatikCraft Project")

    def body(self, master: tk.Misc) -> tk.Widget:
        form = ttk.Frame(master, padding=(8, 8))
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)

        fields = (
            ("Project title", self.title_var),
            ("Creator", self.creator_var),
            ("Canvas width", self.width_var),
            ("Canvas height", self.height_var),
        )
        first_entry: ttk.Entry | None = None
        for row, (label, variable) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 14), pady=6)
            entry = ttk.Entry(form, textvariable=variable, width=38)
            entry.grid(row=row, column=1, sticky="ew", pady=6)
            if first_entry is None:
                first_entry = entry

        ttk.Label(form, text="Background").grid(
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
        ttk.Button(background_row, text="Choose…", command=self._choose_color).grid(
            row=0,
            column=1,
            padx=(8, 0),
        )
        return first_entry or form

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
                "Invalid canvas size",
                "Canvas width and height must be whole numbers.",
                parent=self,
            )
            return False
        except ProjectValidationError as exc:
            messagebox.showerror("Invalid project", str(exc), parent=self)
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
        # Validation already prepared the immutable request object.
        return None

    def _choose_color(self) -> None:
        _rgb, color = colorchooser.askcolor(
            color=self.background_var.get(),
            parent=self,
            title="Choose Canvas Background",
        )
        if color:
            self.background_var.set(color.upper())
