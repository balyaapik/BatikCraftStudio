"""Small transient windows for drawing and object settings."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import colorchooser, ttk
from typing import Any

from batikcraft_studio.imaging import ASSET_CATEGORIES, ISEN_LABELS, MOTIF_LABELS, SUSUN_LABELS


class EditorToolWindows:
    """Own one reusable Toplevel per editor function instead of permanent dock tabs."""

    def __init__(self, editor: Any) -> None:
        self.editor = editor
        self._windows: dict[str, tk.Toplevel] = {}

    def open_brush(self, tool: str = "brush") -> None:
        title = "Pengaturan Kuas" if tool == "brush" else "Pengaturan Penghapus"

        def build(window: tk.Toplevel, body: ttk.Frame) -> None:
            self._number_row(body, 0, "Ukuran", self.editor.brush_size_value, 1, 256, 1)
            self._number_row(
                body,
                1,
                "Opacity (%)",
                self.editor.brush_opacity_value,
                1,
                100,
                1,
            )
            self._number_row(
                body,
                2,
                "Hardness (%)",
                self.editor.brush_hardness_value,
                0,
                100,
                1,
            )
            self._number_row(
                body,
                3,
                "Smoothing (%)",
                self.editor.brush_smoothing_value,
                0,
                100,
                1,
            )
            if tool == "brush":
                self._color_row(body, 4, "Warna", self.editor.brush_color_value)
            ttk.Label(
                body,
                text="Setiap tarikan disimpan sebagai satu objek ber-bounds kecil.",
                style="Muted.TLabel",
                wraplength=280,
                justify="left",
            ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 4))
            command = (
                self.editor.activate_brush_tool
                if tool == "brush"
                else self.editor.activate_eraser_tool
            )
            self._action_row(
                body,
                6,
                primary_label="Aktifkan",
                primary=lambda: self._activate_and_focus(command, window),
                window=window,
            )

        self._show(f"paint-{tool}", title, build)

    def open_shape(self, shape_type: str) -> None:
        labels = {
            "line": "Garis",
            "rectangle": "Persegi",
            "ellipse": "Elips",
            "polygon": "Poligon",
        }
        title = f"Alat {labels.get(shape_type, shape_type.title())}"

        def build(window: tk.Toplevel, body: ttk.Frame) -> None:
            self._number_row(body, 0, "Lebar", self.editor.shape_width_value, 1, 16384, 1)
            self._number_row(body, 1, "Tinggi", self.editor.shape_height_value, 1, 16384, 1)
            ttk.Checkbutton(
                body,
                text="Fill",
                variable=self.editor.shape_fill_enabled,
            ).grid(row=2, column=0, sticky="w", pady=4)
            self._color_button(body, 2, self.editor.shape_fill_color)
            ttk.Checkbutton(
                body,
                text="Stroke",
                variable=self.editor.shape_stroke_enabled,
            ).grid(row=3, column=0, sticky="w", pady=4)
            self._color_button(body, 3, self.editor.shape_stroke_color)
            self._number_row(
                body,
                4,
                "Tebal stroke",
                self.editor.shape_stroke_width,
                0.5,
                128,
                0.5,
            )
            if shape_type == "polygon":
                self._number_row(
                    body,
                    5,
                    "Jumlah sisi",
                    self.editor.shape_polygon_sides,
                    3,
                    12,
                    1,
                )
            ttk.Label(
                body,
                text="Shift membatasi proporsi/sudut. Alt menggambar dari pusat.",
                style="Muted.TLabel",
                wraplength=280,
                justify="left",
            ).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 4))
            self._action_row(
                body,
                7,
                primary_label="Aktifkan",
                primary=lambda: self._activate_and_focus(
                    lambda: self.editor._activate_shape_tool(shape_type),
                    window,
                ),
                secondary_label="Buat di Tengah",
                secondary=lambda: self.editor._new_default_shape(shape_type),
                window=window,
            )

        self._show(f"shape-{shape_type}", title, build)

    def open_motif(self) -> None:
        def build(window: tk.Toplevel, body: ttk.Frame) -> None:
            self._combo_row(
                body,
                0,
                "Motif pokok",
                self.editor.motif_label_value,
                tuple(MOTIF_LABELS.values()),
            )
            self._number_row(body, 1, "Ukuran", self.editor.motif_size_value, 48, 2048, 1)
            self._color_row(body, 2, "Warna motif", self.editor.motif_color_value)
            self._color_row(body, 3, "Warna isen", self.editor.motif_isen_color_value)
            ttk.Checkbutton(
                body,
                text="Isi isen otomatis",
                variable=self.editor.auto_isen_value,
            ).grid(row=4, column=0, columnspan=2, sticky="w", pady=4)
            isen_values = ("Sesuai motif (otomatis)", *ISEN_LABELS.values())
            self._combo_row(
                body,
                5,
                "Isen pengisi",
                self.editor.motif_isen_label_value,
                tuple(isen_values),
            )
            self._combo_row(
                body,
                6,
                "Pola susun",
                self.editor.susun_label_value,
                tuple(SUSUN_LABELS.values()),
            )
            self._action_row(
                body,
                7,
                primary_label="Aktifkan Cap",
                primary=lambda: self._activate_and_focus(
                    self.editor.activate_cap_motif_tool,
                    window,
                ),
                secondary_label="Cap di Tengah",
                secondary=self.editor.cap_motif_di_tengah,
                window=window,
            )

        self._show("motif", "Cap Motif Batik", build)

    def open_isen(self) -> None:
        def build(window: tk.Toplevel, body: ttk.Frame) -> None:
            self._combo_row(
                body,
                0,
                "Jenis isen",
                self.editor.isen_label_value,
                tuple(ISEN_LABELS.values()),
            )
            self._number_row(body, 1, "Ukuran", self.editor.cap_size_value, 8, 1024, 1)
            self._color_row(body, 2, "Warna", self.editor.cap_color_value)
            self._combo_row(
                body,
                3,
                "Pola susun",
                self.editor.susun_label_value,
                tuple(SUSUN_LABELS.values()),
            )
            self._action_row(
                body,
                4,
                primary_label="Aktifkan Cap",
                primary=lambda: self._activate_and_focus(
                    self.editor.activate_cap_isen_tool,
                    window,
                ),
                secondary_label="Cap di Tengah",
                secondary=self.editor.cap_isen_di_tengah,
                window=window,
            )

        self._show("isen", "Cap Isen-Isen", build)

    def open_transform(self) -> None:
        def build(window: tk.Toplevel, body: ttk.Frame) -> None:
            fields = (
                ("X", self.editor.x_value),
                ("Y", self.editor.y_value),
                ("Rotasi", self.editor.rotation_value),
                ("Skala X", self.editor.scale_x_value),
                ("Skala Y", self.editor.scale_y_value),
                ("Opacity", self.editor.opacity_value),
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
            self._action_row(
                body,
                len(fields),
                primary_label="Terapkan",
                primary=self.editor.apply_transform,
                window=window,
            )

        self._show("transform", "Transform Objek", build)

    def open_asset_metadata(self) -> None:
        self.editor._refresh_asset_fields()

        def build(window: tk.Toplevel, body: ttk.Frame) -> None:
            ttk.Label(body, text="Nama", style="Muted.TLabel").grid(
                row=0,
                column=0,
                sticky="w",
                pady=4,
            )
            ttk.Entry(body, textvariable=self.editor.asset_name_value).grid(
                row=0,
                column=1,
                sticky="ew",
                padx=(10, 0),
                pady=4,
            )
            self._combo_row(
                body,
                1,
                "Kategori",
                self.editor.asset_category_value,
                tuple(ASSET_CATEGORIES),
            )
            self._action_row(
                body,
                2,
                primary_label="Terapkan",
                primary=self.editor.apply_asset_metadata,
                window=window,
            )

        self._show("asset-metadata", "Metadata Asset", build)

    def open_humanize(self) -> None:
        self.editor._refresh_asset_fields()

        def build(window: tk.Toplevel, body: ttk.Frame) -> None:
            self._number_row(
                body,
                0,
                "Seed",
                self.editor.humanize_seed_value,
                0,
                999999,
                1,
            )
            self._number_row(
                body,
                1,
                "Tepi tidak rata",
                self.editor.edge_wobble_value,
                0,
                1,
                0.01,
            )
            self._number_row(
                body,
                2,
                "Celah malam",
                self.editor.ink_breaks_value,
                0,
                1,
                0.01,
            )
            self._number_row(
                body,
                3,
                "Variasi tekanan",
                self.editor.pressure_variation_value,
                0,
                1,
                0.01,
            )
            ttk.Label(
                body,
                text=(
                    "Mulai ringan: tepi 0.06–0.14, celah 0.03–0.08, "
                    "tekanan 0.05–0.12. Sumber asli tetap disimpan."
                ),
                style="Muted.TLabel",
                wraplength=300,
                justify="left",
            ).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 4))
            self._action_row(
                body,
                5,
                primary_label="Humanize",
                primary=self.editor.apply_humanize,
                secondary_label="Reset Sumber",
                secondary=self.editor.reset_humanize,
                window=window,
            )

        self._show("humanize", "Humanize Asset", build)

    def _show(
        self,
        key: str,
        title: str,
        builder: Callable[[tk.Toplevel, ttk.Frame], None],
    ) -> None:
        existing = self._windows.get(key)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return
        window = tk.Toplevel(self.editor.winfo_toplevel())
        self._windows[key] = window
        window.title(title)
        window.transient(self.editor.winfo_toplevel())
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", lambda: self._close(key))
        body = ttk.Frame(window, style="Dock.TFrame", padding=(14, 12))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        builder(window, body)
        window.update_idletasks()
        self._center(window)
        window.lift()
        window.focus_force()

    def _close(self, key: str) -> None:
        window = self._windows.pop(key, None)
        if window is not None and window.winfo_exists():
            window.destroy()

    def _activate_and_focus(self, command: Callable[[], object], window: tk.Toplevel) -> None:
        command()
        window.withdraw()
        self.editor.canvas.focus_set()

    @staticmethod
    def _center(window: tk.Toplevel) -> None:
        parent = window.master
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - window.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - window.winfo_height()) // 2)
        window.geometry(f"+{x}+{y}")

    @staticmethod
    def _number_row(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.Variable,
        start: float,
        end: float,
        increment: float,
    ) -> None:
        ttk.Label(parent, text=label, style="Muted.TLabel").grid(
            row=row,
            column=0,
            sticky="w",
            pady=4,
        )
        ttk.Spinbox(
            parent,
            from_=start,
            to=end,
            increment=increment,
            textvariable=variable,
            width=13,
        ).grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=4)

    @staticmethod
    def _combo_row(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> None:
        ttk.Label(parent, text=label, style="Muted.TLabel").grid(
            row=row,
            column=0,
            sticky="w",
            pady=4,
        )
        ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
            width=24,
        ).grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=4)

    def _color_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=label, style="Muted.TLabel").grid(
            row=row,
            column=0,
            sticky="w",
            pady=4,
        )
        self._color_button(parent, row, variable)

    def _color_button(
        self,
        parent: ttk.Frame,
        row: int,
        variable: tk.StringVar,
    ) -> None:
        button = tk.Button(
            parent,
            textvariable=variable,
            background=variable.get(),
            activebackground=variable.get(),
            relief=tk.FLAT,
            borderwidth=1,
            cursor="hand2",
        )

        def choose() -> None:
            _rgb, selected = colorchooser.askcolor(
                color=variable.get(),
                parent=parent.winfo_toplevel(),
            )
            if selected:
                value = selected.upper()
                variable.set(value)
                button.configure(background=value, activebackground=value)

        button.configure(command=choose)
        button.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=4)

    @staticmethod
    def _action_row(
        parent: ttk.Frame,
        row: int,
        *,
        primary_label: str,
        primary: Callable[[], object],
        window: tk.Toplevel,
        secondary_label: str | None = None,
        secondary: Callable[[], object] | None = None,
    ) -> None:
        actions = ttk.Frame(parent, style="Toolbar.TFrame", padding=(3, 3))
        actions.grid(row=row, column=0, columnspan=2, sticky="e", pady=(12, 0))
        if secondary_label and secondary:
            ttk.Button(
                actions,
                text=secondary_label,
                style="Secondary.TButton",
                command=secondary,
            ).pack(side="left", padx=(0, 6))
        ttk.Button(
            actions,
            text=primary_label,
            style="Primary.TButton",
            command=primary,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            actions,
            text="Tutup",
            style="Secondary.TButton",
            command=window.withdraw,
        ).pack(side="left")


__all__ = ["EditorToolWindows"]
