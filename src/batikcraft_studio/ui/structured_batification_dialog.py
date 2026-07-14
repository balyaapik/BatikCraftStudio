"""Small modal dialog for object-aware Structured Batification."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from batikcraft_studio.i18n import tr
from batikcraft_studio.imaging.structured_batification import (
    BatificationError,
    BatificationRequest,
    BatificationStyle,
)


class StructuredBatificationDialog(tk.Toplevel):
    """Collect one serializable Batification request."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        mode: str,
        primary_color: str = "#4E2A1E",
        secondary_color: str = "#D9A566",
        provider_id: str = "local-structured-foundation-v1",
    ) -> None:
        super().__init__(parent)
        self.result: BatificationRequest | None = None
        self._mode = mode
        self._provider_id = provider_id
        self.style_value = tk.StringVar(value=BatificationStyle.CLASSIC.value)
        self.strength_value = tk.DoubleVar(value=72)
        self.density_value = tk.DoubleVar(value=48)
        self.preserve_palette_value = tk.BooleanVar(value=False)
        self.add_filler_value = tk.BooleanVar(value=True)
        self.primary_value = tk.StringVar(value=primary_color)
        self.secondary_value = tk.StringVar(value=secondary_color)
        self.seed_value = tk.StringVar(value="2026")

        self.title(
            tr(
                "ai.dialog.group_title"
                if mode == "group"
                else "ai.dialog.object_title"
            )
        )
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build()
        self.update_idletasks()
        self._center(parent)
        self.grab_set()
        self.focus_set()
        self.wait_window(self)

    def _build(self) -> None:
        body = ttk.Frame(self, padding=14)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(body, text=tr("ai.dialog.provider")).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Label(
            body,
            text=f"{tr('ai.dialog.provider_local')}\n{self._provider_id}",
            style="Muted.TLabel",
            wraplength=360,
            justify="left",
        ).grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        ttk.Label(body, text=tr("ai.dialog.style")).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )
        styles = tuple(style.value for style in BatificationStyle)
        style_combo = ttk.Combobox(
            body,
            textvariable=self.style_value,
            values=styles,
            state="readonly",
            width=25,
        )
        style_combo.grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        ttk.Label(body, text=tr("ai.dialog.strength")).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )
        tk.Scale(
            body,
            variable=self.strength_value,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            showvalue=True,
            resolution=1,
            length=280,
        ).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        ttk.Label(body, text=tr("ai.dialog.density")).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )
        tk.Scale(
            body,
            variable=self.density_value,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            showvalue=True,
            resolution=1,
            length=280,
        ).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        ttk.Checkbutton(
            body,
            text=tr("ai.dialog.preserve_palette"),
            variable=self.preserve_palette_value,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
        row += 1
        ttk.Checkbutton(
            body,
            text=tr("ai.dialog.add_filler"),
            variable=self.add_filler_value,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
        row += 1

        self._color_row(body, row, "ai.dialog.primary", self.primary_value)
        row += 1
        self._color_row(body, row, "ai.dialog.secondary", self.secondary_value)
        row += 1

        ttk.Label(body, text=tr("ai.dialog.seed")).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Spinbox(
            body,
            from_=0,
            to=2_147_483_647,
            textvariable=self.seed_value,
            width=20,
        ).grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        ttk.Label(body, text=tr("ai.dialog.prompt")).grid(
            row=row, column=0, sticky="nw", padx=(0, 10), pady=4
        )
        self.prompt_text = tk.Text(body, width=42, height=4, wrap="word")
        self.prompt_text.grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        ttk.Label(
            body,
            text=tr("ai.dialog.foundation_note"),
            style="Muted.TLabel",
            wraplength=500,
            justify="left",
        ).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 12))
        row += 1

        actions = ttk.Frame(body)
        actions.grid(row=row, column=0, columnspan=2, sticky="e")
        ttk.Button(
            actions,
            text=tr("common.cancel"),
            command=self._cancel,
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            actions,
            text=tr("ai.dialog.render"),
            command=self._accept,
        ).pack(side="right")

    def _color_row(
        self,
        parent: ttk.Frame,
        row: int,
        label_key: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=tr(label_key)).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )
        holder = ttk.Frame(parent)
        holder.grid(row=row, column=1, sticky="w", pady=4)
        ttk.Entry(holder, textvariable=variable, width=12).pack(side="left")
        preview = tk.Button(
            holder,
            width=3,
            background=variable.get(),
            activebackground=variable.get(),
        )
        preview.configure(command=lambda: self._choose_color(variable, preview))
        preview.pack(side="left", padx=(6, 0))

    def _choose_color(self, variable: tk.StringVar, preview: tk.Button) -> None:
        _rgb, selected = colorchooser.askcolor(
            color=variable.get(),
            parent=self,
            title=tr("common.color"),
        )
        if selected:
            color = selected.upper()
            variable.set(color)
            preview.configure(background=color, activebackground=color)

    def _accept(self) -> None:
        try:
            seed = int(self.seed_value.get().strip())
            request = BatificationRequest(
                style=BatificationStyle(self.style_value.get()),
                strength=self.strength_value.get() / 100,
                isen_density=self.density_value.get() / 100,
                preserve_palette=self.preserve_palette_value.get(),
                primary_color=self.primary_value.get(),
                secondary_color=self.secondary_value.get(),
                seed=seed,
                add_filler=self.add_filler_value.get(),
                prompt=self.prompt_text.get("1.0", "end").strip(),
            )
        except (BatificationError, TypeError, ValueError) as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self.result = request
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center(self, parent: tk.Misc) -> None:
        top = parent.winfo_toplevel()
        x = top.winfo_rootx() + max(0, (top.winfo_width() - self.winfo_width()) // 2)
        y = top.winfo_rooty() + max(0, (top.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")


__all__ = ["StructuredBatificationDialog"]
