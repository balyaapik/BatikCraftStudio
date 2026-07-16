"""Choose between one isolated ornament and a full repeating pattern."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from batikcraft_studio.ai.batikbrew_generation_modes import (
    OUTPUT_MODE_ORNAMENT,
    OUTPUT_MODE_PATTERN,
)


class BatikBrewOutputModeDialog(tk.Toplevel):
    """Modal selector with visible actions and keyboard confirmation."""

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

        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

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

        first_radio: ttk.Radiobutton | None = None
        for row, (value, title, description) in enumerate(
            (
                (
                    OUTPUT_MODE_ORNAMENT,
                    "Ornamen Tunggal",
                    "Menghasilkan satu ornamen Batik terisolasi. Tidak diulang, tidak "
                    "memenuhi seluruh gambar, dan background dibuang menjadi transparan.",
                ),
                (
                    OUTPUT_MODE_PATTERN,
                    "Pola",
                    "Menghasilkan komposisi motif penuh seperti kain/pattern. Dapat "
                    "dibuat seamless dan diulang sebagai tile.",
                ),
            )
        ):
            card = ttk.LabelFrame(choices, text=title, padding=10)
            card.grid(row=row, column=0, sticky="ew", pady=5)
            radio = ttk.Radiobutton(
                card,
                text=title,
                value=value,
                variable=self.value,
            )
            radio.pack(anchor="w")
            ttk.Label(
                card,
                text=description,
                wraplength=515,
                justify="left",
                style="Muted.TLabel",
            ).pack(anchor="w", padx=(24, 0), pady=(2, 0))
            card.bind("<Double-Button-1>", self._accept_event)
            radio.bind("<Double-Button-1>", self._accept_event)
            if first_radio is None:
                first_radio = radio

        separator = ttk.Separator(body, orient="horizontal")
        separator.grid(row=3, column=0, sticky="ew", pady=(14, 10))

        actions = ttk.Frame(body)
        actions.grid(row=4, column=0, sticky="ew")
        ttk.Label(
            actions,
            text="Enter: lanjutkan  •  Esc: batal",
            style="Muted.TLabel",
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Batal",
            command=self._cancel,
        ).pack(side="right", padx=(6, 0))
        self.continue_button = ttk.Button(
            actions,
            text="OK / Lanjutkan",
            command=self._accept,
        )
        self.continue_button.pack(side="right")

        self.bind("<Return>", self._accept_event)
        self.bind("<KP_Enter>", self._accept_event)
        self.bind("<Escape>", self._cancel_event)

        self.update_idletasks()
        self.grab_set()
        if first_radio is not None:
            first_radio.focus_set()

    def _accept_event(self, _event: tk.Event[tk.Misc]) -> str:
        self._accept()
        return "break"

    def _cancel_event(self, _event: tk.Event[tk.Misc]) -> str:
        self._cancel()
        return "break"

    def _accept(self) -> None:
        selected = self.value.get()
        if selected not in {OUTPUT_MODE_ORNAMENT, OUTPUT_MODE_PATTERN}:
            return
        self.result = selected
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = ["BatikBrewOutputModeDialog"]