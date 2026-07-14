"""Transform dialog extension for affine WYSIWYG editing."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from batikcraft_studio.i18n import tr

from .tool_windows import EditorToolWindows


class WysiwygToolWindows(EditorToolWindows):
    """Show the complete move, rotation, scale, shear, and opacity model."""

    def __init__(self, editor: Any) -> None:
        super().__init__(editor)

    def open_transform(self) -> None:
        self.editor._refresh_transform_fields()

        def build(window: tk.Toplevel, body: ttk.Frame) -> None:
            fields = (
                ("X", self.editor.x_value),
                ("Y", self.editor.y_value),
                (tr("common.rotation"), self.editor.rotation_value),
                (tr("tool.scale_x"), self.editor.scale_x_value),
                (tr("tool.scale_y"), self.editor.scale_y_value),
                (tr("gizmo.shear_x"), self.editor.shear_x_value),
                (tr("gizmo.shear_y"), self.editor.shear_y_value),
                (tr("common.opacity"), self.editor.opacity_value),
            )
            for row, (label, variable) in enumerate(fields):
                ttk.Label(body, text=label, style="Muted.TLabel").grid(
                    row=row,
                    column=0,
                    sticky="w",
                    pady=4,
                )
                ttk.Entry(body, textvariable=variable, width=15).grid(
                    row=row,
                    column=1,
                    sticky="ew",
                    padx=(10, 0),
                    pady=4,
                )
            ttk.Label(
                body,
                text=tr("gizmo.dialog_note"),
                style="Muted.TLabel",
                wraplength=300,
                justify="left",
            ).grid(row=len(fields), column=0, columnspan=2, sticky="ew", pady=(8, 0))
            self._action_row(
                body,
                len(fields) + 1,
                primary_label=tr("common.apply"),
                primary=self.editor.apply_transform,
                window=window,
            )

        self._show("transform", tr("tool.transform.title"), build)


__all__ = ["WysiwygToolWindows"]
