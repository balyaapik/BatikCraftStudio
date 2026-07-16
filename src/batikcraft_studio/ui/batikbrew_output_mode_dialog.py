"""Choose between one isolated ornament and a full repeating pattern."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from batikcraft_studio.ai.batikbrew_generation_modes import (
    OUTPUT_MODE_ORNAMENT,
    OUTPUT_MODE_PATTERN,
)


class BatikBrewOutputModeDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.result: str | None = None
        self.value = tk.StringVar(master=self, value=OUTPUT_MODE_ORNAMENT)
        self.title("Jenis Hasil BatikBrew")
        self.geometry("560x330")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Pilih jenis hasil AI", font=("TkDefaultFont", 15, "bold")).pack(anchor="w")
        ttk.Label(
            body,
            text="Mode ini menentukan apakah SDXL membuat satu ornamen transparan atau satu bidang pola penuh.",
            wraplength=510,
            justify="left",
        ).pack(anchor="w", pady=(4, 14))

        for value, title, description in (
            (
                OUTPUT_MODE_ORNAMENT,
                "Ornamen Tunggal",
                "Menghasilkan satu ornamen Batik terisolasi. Tidak diulang, tidak memenuhi seluruh gambar, dan background dibuang menjadi transparan.",
            ),
            (
                OUTPUT_MODE_PATTERN,
                "Pola",
                "Menghasilkan komposisi motif penuh seperti kain/pattern. Dapat dibuat seamless dan diulang sebagai tile.",
            ),
        ):
            card = ttk.LabelFrame(body, text=title, padding=10)
            card.pack(fill="x", pady=5)
            ttk.Radiobutton(card, text=title, value=value, variable=self.value).pack(anchor="w")
            ttk.Label(card, text=description, wraplength=475, justify="left", style="Muted.TLabel").pack(anchor="w", padx=(24, 0), pady=(2, 0))

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Batal", command=self._cancel).pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="Lanjutkan", command=self._accept).pack(side="right")
        self.grab_set()
        self.focus_set()

    def _accept(self) -> None:
        self.result = self.value.get()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = ["BatikBrewOutputModeDialog"]
