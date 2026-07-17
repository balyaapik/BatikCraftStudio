"""Expanded Humanize effect controls for selected Batik objects."""

from __future__ import annotations

import random
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Any


@dataclass(frozen=True, slots=True)
class HumanizePreset:
    label: str
    edge_wobble: float
    ink_breaks: float
    pressure_variation: float
    description: str


HUMANIZE_PRESETS: dict[str, HumanizePreset] = {
    "subtle": HumanizePreset(
        "Halus",
        0.08,
        0.03,
        0.06,
        "Sedikit ketidakteraturan untuk hasil yang tetap bersih dan modern.",
    ),
    "canting": HumanizePreset(
        "Canting Natural",
        0.18,
        0.08,
        0.12,
        "Variasi seimbang yang menyerupai sapuan canting manual.",
    ),
    "expressive": HumanizePreset(
        "Tulis Ekspresif",
        0.34,
        0.16,
        0.22,
        "Tepi, celah malam, dan tekanan lebih kuat untuk karakter handmade.",
    ),
    "vintage": HumanizePreset(
        "Kain Tua",
        0.24,
        0.25,
        0.30,
        "Tekstur aus dengan celah dan variasi opacity yang lebih kentara.",
    ),
}


class EnhancedHumanizeWindow(tk.Toplevel):
    """Apply deterministic Humanize presets and custom values to one object."""

    def __init__(self, parent: tk.Misc, editor: Any) -> None:
        super().__init__(parent)
        self.editor = editor
        self.preset_by_label = {
            preset.label: key for key, preset in HUMANIZE_PRESETS.items()
        }
        self.preset_value = tk.StringVar(master=self, value="Canting Natural")
        self.description_value = tk.StringVar(master=self)

        refresh = getattr(editor, "_refresh_asset_fields", None)
        if callable(refresh):
            refresh()

        self.title("Effects — Humanize")
        self.geometry("620x470")
        self.minsize(560, 430)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._build()
        self._refresh_description()
        self.grab_set()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(
            body,
            text="Humanize Batik",
            font=("TkDefaultFont", 16, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            body,
            text=(
                "Menambahkan ketidakteraturan deterministik pada tepi, tekanan, dan "
                "celah malam. Asset sumber tetap tersimpan sehingga efek dapat di-reset."
            ),
            style="Muted.TLabel",
            wraplength=570,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 14))

        ttk.Label(body, text="Preset").grid(row=2, column=0, sticky="w", pady=5)
        preset_combo = ttk.Combobox(
            body,
            textvariable=self.preset_value,
            values=tuple(self.preset_by_label),
            state="readonly",
        )
        preset_combo.grid(row=2, column=1, sticky="ew", padx=(10, 8), pady=5)
        preset_combo.bind("<<ComboboxSelected>>", lambda _event: self._choose_preset())
        ttk.Button(body, text="Terapkan Preset", command=self._choose_preset).grid(
            row=2,
            column=2,
            pady=5,
        )
        ttk.Label(
            body,
            textvariable=self.description_value,
            style="Muted.TLabel",
            wraplength=570,
            justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 10))

        self._number_row(
            body,
            4,
            "Seed",
            self.editor.humanize_seed_value,
            0,
            999999,
            1,
        )
        self._number_row(
            body,
            5,
            "Ketidakteraturan tepi",
            self.editor.edge_wobble_value,
            0,
            1,
            0.01,
        )
        self._number_row(
            body,
            6,
            "Celah malam / tinta",
            self.editor.ink_breaks_value,
            0,
            1,
            0.01,
        )
        self._number_row(
            body,
            7,
            "Variasi tekanan / opacity",
            self.editor.pressure_variation_value,
            0,
            1,
            0.01,
        )

        tools = ttk.Frame(body)
        tools.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Button(
            tools,
            text="Acak Seed",
            command=self.randomize_seed,
        ).pack(side="left")
        ttk.Button(
            tools,
            text="Reset ke Asset Sumber",
            command=self._reset,
        ).pack(side="left", padx=(8, 0))

        actions = ttk.Frame(body)
        actions.grid(row=9, column=0, columnspan=3, sticky="e", pady=(18, 0))
        ttk.Button(actions, text="Tutup", command=self.destroy).pack(
            side="right",
            padx=(8, 0),
        )
        ttk.Button(actions, text="Terapkan Humanize", command=self._apply).pack(
            side="right"
        )

        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Control-Return>", lambda _event: self._apply())

    @staticmethod
    def _number_row(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.Variable,
        start: float,
        stop: float,
        increment: float,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Spinbox(
            parent,
            from_=start,
            to=stop,
            increment=increment,
            textvariable=variable,
        ).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=5)

    def _choose_preset(self) -> None:
        key = self.preset_by_label.get(self.preset_value.get(), "canting")
        preset = HUMANIZE_PRESETS[key]
        self.editor.edge_wobble_value.set(preset.edge_wobble)
        self.editor.ink_breaks_value.set(preset.ink_breaks)
        self.editor.pressure_variation_value.set(preset.pressure_variation)
        self._refresh_description()

    def _refresh_description(self) -> None:
        key = self.preset_by_label.get(self.preset_value.get(), "canting")
        self.description_value.set(HUMANIZE_PRESETS[key].description)

    def randomize_seed(self) -> None:
        self.editor.humanize_seed_value.set(random.SystemRandom().randint(0, 999999))

    def _apply(self) -> None:
        try:
            self.editor.apply_humanize()
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Humanize gagal", str(exc), parent=self)

    def _reset(self) -> None:
        self.editor.reset_humanize()


def apply_humanize_preset(editor: Any, preset_key: str) -> None:
    """Apply one named preset through the editor's existing undoable workflow."""

    try:
        preset = HUMANIZE_PRESETS[preset_key]
    except KeyError as exc:
        raise ValueError(f"Preset Humanize tidak dikenal: {preset_key}") from exc
    editor.edge_wobble_value.set(preset.edge_wobble)
    editor.ink_breaks_value.set(preset.ink_breaks)
    editor.pressure_variation_value.set(preset.pressure_variation)
    editor.apply_humanize()


__all__ = [
    "EnhancedHumanizeWindow",
    "HUMANIZE_PRESETS",
    "HumanizePreset",
    "apply_humanize_preset",
]
