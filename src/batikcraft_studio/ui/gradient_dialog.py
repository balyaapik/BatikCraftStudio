"""Dialog gradasi warna objek: linear/radial, dua warna, sudut, opasitas."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk
from typing import Any, Callable


class ObjectGradientDialog(tk.Toplevel):
    """Kumpulkan pengaturan gradasi lalu terapkan lewat callback pemanggil."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        start_color: str,
        end_color: str,
        on_apply: Callable[[str, dict[str, Any] | None], None],
    ) -> None:
        super().__init__(parent)
        self.title("Gradasi Warna Objek")
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self._on_apply = on_apply

        body = ttk.Frame(self, padding=(12, 10))
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        self.mode_value = tk.StringVar(master=self, value="linear_gradient")
        ttk.Label(body, text="Jenis gradasi:").grid(row=0, column=0, sticky="w")
        mode_row = ttk.Frame(body)
        mode_row.grid(row=0, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(
            mode_row, text="Linear", value="linear_gradient", variable=self.mode_value
        ).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            mode_row, text="Radial", value="radial_gradient", variable=self.mode_value
        ).pack(side="left")

        self.start_value = tk.StringVar(master=self, value=start_color.upper())
        self.end_value = tk.StringVar(master=self, value=end_color.upper())
        self._color_row(body, 1, "Warna awal/pusat:", self.start_value)
        self._color_row(body, 2, "Warna akhir/tepi:", self.end_value)

        ttk.Label(body, text="Sudut (linear):").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.angle_value = tk.DoubleVar(master=self, value=0.0)
        angle = ttk.Scale(
            body, from_=0, to=360, variable=self.angle_value, orient="horizontal"
        )
        angle.grid(row=3, column=1, sticky="ew", padx=(6, 4), pady=(6, 0))
        self.angle_label = ttk.Label(body, text="0°", width=5)
        self.angle_label.grid(row=3, column=2, sticky="e", pady=(6, 0))
        self.angle_value.trace_add(
            "write",
            lambda *_a: self.angle_label.configure(
                text=f"{round(self.angle_value.get())}°"
            ),
        )

        ttk.Label(body, text="Opasitas awal:").grid(row=4, column=0, sticky="w")
        self.start_opacity = tk.DoubleVar(master=self, value=100.0)
        ttk.Scale(
            body, from_=0, to=100, variable=self.start_opacity, orient="horizontal"
        ).grid(row=4, column=1, columnspan=2, sticky="ew", padx=(6, 0))
        ttk.Label(body, text="Opasitas akhir:").grid(row=5, column=0, sticky="w")
        self.end_opacity = tk.DoubleVar(master=self, value=100.0)
        ttk.Scale(
            body, from_=0, to=100, variable=self.end_opacity, orient="horizontal"
        ).grid(row=5, column=1, columnspan=2, sticky="ew", padx=(6, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        buttons.columnconfigure(0, weight=1)
        ttk.Button(
            buttons, text="Hapus Gradasi", command=self._clear
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(buttons, text="Batal", command=self.destroy).grid(
            row=0, column=1, sticky="e", padx=(0, 6)
        )
        ttk.Button(
            buttons, text="Terapkan", style="Accent.TButton", command=self._apply
        ).grid(row=0, column=2, sticky="e")

    def _color_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(6, 0))
        swatch = tk.Button(
            parent,
            textvariable=variable,
            background=variable.get(),
            activebackground=variable.get(),
            width=10,
            relief=tk.RAISED,
            cursor="hand2",
        )

        def choose() -> None:
            _rgb, selected = colorchooser.askcolor(
                color=variable.get(), parent=self, title=label
            )
            if selected:
                variable.set(selected.upper())
                swatch.configure(background=selected, activebackground=selected)

        swatch.configure(command=choose)
        swatch.grid(row=row, column=1, columnspan=2, sticky="w", padx=(6, 0), pady=(6, 0))

    def _gradient_dict(self, mode: str) -> dict[str, Any]:
        start = self.start_value.get()
        end = self.end_value.get()
        if mode == "radial_gradient":
            return {
                "center_color": start,
                "outer_color": end,
                "center_opacity": self.start_opacity.get() / 100.0,
                "outer_opacity": self.end_opacity.get() / 100.0,
                "center_x": 0.5,
                "center_y": 0.5,
                "radius": 0.75,
            }
        return {
            "start_color": start,
            "end_color": end,
            "angle": float(self.angle_value.get()),
            "start_opacity": self.start_opacity.get() / 100.0,
            "end_opacity": self.end_opacity.get() / 100.0,
        }

    def _apply(self) -> None:
        mode = self.mode_value.get()
        self._on_apply(mode, self._gradient_dict(mode))
        self.destroy()

    def _clear(self) -> None:
        self._on_apply("solid", None)
        self.destroy()


__all__ = ["ObjectGradientDialog"]
