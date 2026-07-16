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
        self.geometry("620x470")
        self.minsize(580, 430)
        self.resizable(True, True)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Return>", lambda _event: self._accept())
        self.bind("<KP_Enter>", lambda _event: self._accept())
        self.bind("<Escape>", lambda _event: self._cancel())

        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)

        ttk.Label(
            body,
            text="Pilih jenis hasil AI",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text=(
                "Mode ini menentukan apakah SDXL membuat satu ornamen transparan "
                "atau satu bidang pola penuh."
            ),
            wraplength=560,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 14))

        choices = ttk.Frame(body)
        choices.grid(row=2, column=0, sticky="nsew")
        choices.columnconfigure(0, weight=1)

        for value, title, description in (
            (
                OUTPUT_MODE_ORNAMENT,
                "Ornamen Tunggal",
                "Menghasilkan satu ornamen Batik terisolasi. Tidak diulang, tidak "
                "memenuhi seluruh gambar, dan background dibuang menjadi transparan.",
            ),
            (
                OUTPUT_MODE_PATTERN,
                "Pola",
                "Menghasilkan komposisi motif penuh seperti kain/pattern. Dapat dibuat "
                "seamless dan diulang sebagai tile.",
            ),
        ):
            card = ttk.LabelFrame(choices, text=title, padding=12)
            card.pack(fill="x", pady=6)
            ttk.Radiobutton(
                card,
                text=title,
                value=value,
                variable=self.value,
                command=self._refresh_summary,
            ).pack(anchor="w")
            ttk.Label(
                card,
                text=description,
                wraplength=520,
                justify="left",
                style="Muted.TLabel",
            ).pack(anchor="w", padx=(24, 0), pady=(3, 0))

        self.summary = ttk.Label(
            body,
            text="",
            style="Muted.TLabel",
            wraplength=560,
            justify="left",
        )
        self.summary.grid(row=3, column=0, sticky="sew", pady=(12, 8))

        actions = ttk.Frame(body)
        actions.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        ttk.Label(
            actions,
            text="Enter: OK / Lanjutkan   •   Esc: Batal",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text="Batal", command=self._cancel).grid(
            row=0,
            column=1,
            padx=(8, 0),
        )
        self.accept_button = ttk.Button(
            actions,
            text="OK / Lanjutkan",
            command=self._accept,
            default="active",
        )
        self.accept_button.grid(row=0, column=2, padx=(8, 0))

        self._refresh_summary()
        self.grab_set()
        self.accept_button.focus_set()
        self.after_idle(self._fit_to_content)

    def _fit_to_content(self) -> None:
        """Keep action buttons visible on Windows DPI scaling."""

        self.update_idletasks()
        required_width = max(580, self.winfo_reqwidth())
        required_height = max(430, self.winfo_reqheight())
        self.geometry(f"{required_width}x{required_height}")

    def _refresh_summary(self) -> None:
        if self.value.get() == OUTPUT_MODE_ORNAMENT:
            text = "Pilihan aktif: Ornamen Tunggal — hasil berupa PNG transparan terisolasi."
        else:
            text = "Pilihan aktif: Pola — hasil berupa bidang motif penuh dan dapat dibuat tileable."
        self.summary.configure(text=text)

    def _accept(self) -> None:
        self.result = self.value.get()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = ["BatikBrewOutputModeDialog"]
