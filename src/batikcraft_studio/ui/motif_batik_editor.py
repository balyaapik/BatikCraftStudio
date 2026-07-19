"""Motif-pokok controls with automatic isen filling for the batik editor."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk

from batikcraft_studio.application import MotifCapError, MotifProjectSession
from batikcraft_studio.imaging.isen import ISEN_LABELS, IsenError, symmetry_placements
from batikcraft_studio.imaging.motif import (
    DEFAULT_MOTIF_ISEN,
    MOTIF_LABELS,
    MotifError,
)

from .selectable_batik_editor import SelectableBatikEditorWorkspaceView
from .theme import COLORS
from .widgets import icon_button

_MOTIF_BY_LABEL = {label: key for key, label in MOTIF_LABELS.items()}
_ISEN_BY_LABEL = {label: key for key, label in ISEN_LABELS.items()}
_AUTO_ISEN_LABEL = "Sesuai motif (otomatis)"


class MotifBatikEditorWorkspaceView(SelectableBatikEditorWorkspaceView):
    """Add complete motif-pokok caps while retaining manual Cap Isen tools."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        parent = args[0] if args else kwargs["parent"]
        self.motif_label_value = tk.StringVar(master=parent, value=MOTIF_LABELS["kawung"])
        self.motif_size_value = tk.DoubleVar(master=parent, value=220.0)
        self.motif_color_value = tk.StringVar(master=parent, value="#4E2A1E")
        self.motif_isen_color_value = tk.StringVar(master=parent, value="#8B5A2B")
        self.motif_isen_label_value = tk.StringVar(master=parent, value=_AUTO_ISEN_LABEL)
        self.auto_isen_value = tk.BooleanVar(master=parent, value=True)
        self._motif_press_point: tuple[float, float] | None = None
        super().__init__(*args, **kwargs)
        for variable in (
            self.motif_label_value,
            self.motif_size_value,
            self.motif_isen_label_value,
            self.auto_isen_value,
        ):
            variable.trace_add("write", lambda *_args: self._refresh_cap_preview())

    def _build_batik_panel(self, parent: ttk.Frame) -> None:
        super()._build_batik_panel(parent)
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=14,
            column=0,
            sticky="ew",
            pady=(16, 12),
        )
        ttk.Label(parent, text="Motif Pokok", style="PanelTitle.TLabel").grid(
            row=15,
            column=0,
            sticky="ew",
        )
        ttk.Label(
            parent,
            text="Motif dibentuk lengkap dan bidangnya diisi isen secara otomatis.",
            style="Muted.TLabel",
            wraplength=250,
            justify="left",
        ).grid(row=16, column=0, sticky="ew", pady=(3, 9))

        ttk.Label(parent, text="Jenis motif", style="Muted.TLabel").grid(
            row=17,
            column=0,
            sticky="w",
        )
        ttk.Combobox(
            parent,
            textvariable=self.motif_label_value,
            values=tuple(MOTIF_LABELS.values()),
            state="readonly",
        ).grid(row=18, column=0, sticky="ew", pady=(3, 8))

        ttk.Label(parent, text="Ukuran motif", style="Muted.TLabel").grid(
            row=19,
            column=0,
            sticky="w",
        )
        size_row = ttk.Frame(parent, style="Dock.TFrame")
        size_row.grid(row=20, column=0, sticky="ew", pady=(3, 8))
        size_row.columnconfigure(0, weight=1)
        ttk.Scale(
            size_row,
            from_=48,
            to=768,
            variable=self.motif_size_value,
            orient=tk.HORIZONTAL,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Spinbox(
            size_row,
            from_=48,
            to=2048,
            increment=1,
            textvariable=self.motif_size_value,
            width=7,
        ).grid(row=0, column=1, padx=(8, 0))

        color_grid = ttk.Frame(parent, style="Dock.TFrame")
        color_grid.grid(row=21, column=0, sticky="ew", pady=(3, 8))
        color_grid.columnconfigure(0, weight=1)
        color_grid.columnconfigure(1, weight=1)
        ttk.Label(color_grid, text="Garis motif", style="Muted.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Label(color_grid, text="Warna isen", style="Muted.TLabel").grid(
            row=0,
            column=1,
            sticky="w",
            padx=(6, 0),
        )
        self.motif_color_swatch = self._color_swatch(
            color_grid,
            self.motif_color_value,
            self._choose_motif_color,
            "Pilih warna garis motif pokok",
        )
        self.motif_color_swatch.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self.motif_isen_color_swatch = self._color_swatch(
            color_grid,
            self.motif_isen_color_value,
            self._choose_motif_isen_color,
            "Pilih warna isen pengisi",
        )
        self.motif_isen_color_swatch.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(6, 0),
            pady=(3, 0),
        )

        ttk.Checkbutton(
            parent,
            text="Isi isen otomatis",
            variable=self.auto_isen_value,
        ).grid(row=22, column=0, sticky="w", pady=(2, 5))
        ttk.Label(parent, text="Isen pengisi", style="Muted.TLabel").grid(
            row=23,
            column=0,
            sticky="w",
        )
        ttk.Combobox(
            parent,
            textvariable=self.motif_isen_label_value,
            values=(_AUTO_ISEN_LABEL, *ISEN_LABELS.values()),
            state="readonly",
        ).grid(row=24, column=0, sticky="ew", pady=(3, 8))

        actions = ttk.Frame(parent, style="Dock.TFrame")
        actions.grid(row=25, column=0, sticky="e")
        activate = icon_button(
            actions,
            icon="batikification",
            tooltip="Aktifkan Cap Motif (M)",
            command=self.activate_cap_motif_tool,
            size=20,
        )
        activate.pack(side="left", padx=(0, 4))
        center = icon_button(
            actions,
            icon="apply",
            tooltip="Cap motif lengkap di tengah kain",
            command=self.cap_motif_di_tengah,
            size=20,
        )
        center.pack(side="left")
        ttk.Label(
            parent,
            text=(
                "M  Cap Motif lengkap\n"
                "C  Cap Isen manual\n"
                "Isi otomatis aktif secara bawaan"
            ),
            style="Muted.TLabel",
            justify="left",
        ).grid(row=26, column=0, sticky="w", pady=(9, 0))
        self.bind_all("<Key-m>", self._activate_motif_shortcut)

    def _build_layer_panel(self, parent: ttk.Frame) -> None:
        super()._build_layer_panel(parent)
        submenu_path = self._layer_context_menu.entrycget(0, "menu")
        new_layer_menu = self._layer_context_menu.nametowidget(submenu_path)
        motif_menu = tk.Menu(new_layer_menu, tearoff=False)
        for motif_type, label in MOTIF_LABELS.items():
            motif_menu.add_command(
                label=label,
                command=lambda kind=motif_type: self._new_motif_layer(kind),
            )
        new_layer_menu.add_separator()
        new_layer_menu.add_cascade(label="Motif Pokok", menu=motif_menu)

    def activate_cap_motif_tool(self) -> None:
        self._set_active_tool(
            "cap_motif",
            "Cap Motif aktif — klik kain untuk menempatkan motif lengkap.",
        )

    def _activate_motif_shortcut(self, event: tk.Event[tk.Misc]) -> str | None:
        if self._event_targets_text_input(event):
            return None
        self.activate_cap_motif_tool()
        return "break"

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "cap_motif":
            super()._on_canvas_press(event)
            return
        self._motif_press_point = self._project_point(event.x, event.y)

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "cap_motif":
            super()._on_canvas_drag(event)

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "cap_motif":
            super()._on_canvas_release(event)
            return
        point = self._project_point(event.x, event.y) or self._motif_press_point
        self._motif_press_point = None
        if point is not None:
            self._cap_motif_at(point)

    def cap_motif_di_tengah(self) -> None:
        project = self.session.project
        if project is None:
            self.set_status("Buat atau buka proyek sebelum menggunakan Cap Motif.")
            return
        self._cap_motif_at((project.canvas.width / 2, project.canvas.height / 2))

    def _cap_motif_at(self, point: tuple[float, float]) -> None:
        try:
            layers = self._motif_session.cap_motif(
                self._motif_type(),
                point,
                ukuran=float(self.motif_size_value.get()),
                warna_motif=self.motif_color_value.get(),
                warna_isen=self.motif_isen_color_value.get(),
                isen_type=self._motif_isen_type(),
                isi_isen_otomatis=bool(self.auto_isen_value.get()),
                susun=self._susun_type(),
            )
        except (MotifCapError, MotifError, IsenError, ValueError) as exc:
            self.set_status(str(exc))
            return
        announce = getattr(self, "_announce_bounded_change", None)
        dirty = getattr(self, "_objects_dirty_bounds", None)
        if announce is not None and dirty is not None:
            announce(dirty(layers))
        self.refresh_context()
        motif_label = MOTIF_LABELS[self._motif_type()]
        self.set_status(f"Motif {motif_label} selesai dibuat dalam {len(layers)} lapis.")

    def _new_motif_layer(self, motif_type: str) -> None:
        if not self.session.has_project:
            self.set_status("Buat atau buka proyek sebelum menambah motif pokok.")
            return
        try:
            layers = self._motif_session.cap_motif_di_tengah(
                motif_type,
                ukuran=float(self.motif_size_value.get()),
                warna_motif=self.motif_color_value.get(),
                warna_isen=self.motif_isen_color_value.get(),
                isen_type=self._selected_or_default_isen(motif_type),
                isi_isen_otomatis=bool(self.auto_isen_value.get()),
                susun="tunggal",
            )
        except (MotifCapError, ValueError) as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(f"Motif pokok dibuat: {layers[0].name}")

    def _choose_motif_color(self) -> None:
        _rgb, selected = colorchooser.askcolor(
            color=self.motif_color_value.get(),
            parent=self.winfo_toplevel(),
            title="Pilih Warna Motif Pokok",
        )
        if selected:
            self.motif_color_value.set(selected.upper())
            self.motif_color_swatch.configure(
                background=selected,
                activebackground=selected,
            )

    def _choose_motif_isen_color(self) -> None:
        _rgb, selected = colorchooser.askcolor(
            color=self.motif_isen_color_value.get(),
            parent=self.winfo_toplevel(),
            title="Pilih Warna Isen Pengisi",
        )
        if selected:
            self.motif_isen_color_value.set(selected.upper())
            self.motif_isen_color_swatch.configure(
                background=selected,
                activebackground=selected,
            )

    def _refresh_cap_preview(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("cap-motif-preview")
        if self._active_tool != "cap_motif":
            super()._refresh_cap_preview()
            return
        if self._cap_cursor_position is None:
            return
        project = self.session.project
        point = self._project_point(*self._cap_cursor_position)
        if project is None or point is None:
            return
        try:
            placements = symmetry_placements(
                point,
                canvas_width=project.canvas.width,
                canvas_height=project.canvas.height,
                susun=self._susun_type(),
            )
            radius = max(3.0, float(self.motif_size_value.get()) * self._preview_scale / 2)
        except (IsenError, ValueError, tk.TclError):
            return
        for placement in placements:
            x = self._preview_left + placement.x * self._preview_scale
            y = self._preview_top + placement.y * self._preview_scale
            self.canvas.create_rectangle(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                outline="#FFFFFF",
                width=3,
                tags="cap-motif-preview",
            )
            self.canvas.create_rectangle(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                outline=COLORS["accent_dark"],
                width=1,
                dash=(5, 3),
                tags="cap-motif-preview",
            )
        self.canvas.tag_raise("cap-motif-preview")

    def _on_cap_cursor_leave(self, event: tk.Event[tk.Canvas]) -> None:
        super()._on_cap_cursor_leave(event)
        self.canvas.delete("cap-motif-preview")

    def _set_active_tool(self, tool: str, status: str) -> None:
        super()._set_active_tool(tool, status)
        self.canvas.delete("cap-motif-preview")
        self._refresh_cap_preview()

    def _motif_type(self) -> str:
        return _MOTIF_BY_LABEL.get(self.motif_label_value.get(), "kawung")

    def _motif_isen_type(self) -> str | None:
        selected = self.motif_isen_label_value.get()
        if selected == _AUTO_ISEN_LABEL:
            return None
        return _ISEN_BY_LABEL.get(selected)

    def _selected_or_default_isen(self, motif_type: str) -> str:
        return self._motif_isen_type() or DEFAULT_MOTIF_ISEN[motif_type]

    @property
    def _motif_session(self) -> MotifProjectSession:
        if not isinstance(self.session, MotifProjectSession):
            raise RuntimeError("Editor memerlukan project session yang mendukung Motif Pokok.")
        return self.session


__all__ = ["MotifBatikEditorWorkspaceView"]
