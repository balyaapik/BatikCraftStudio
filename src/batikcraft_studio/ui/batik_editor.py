"""Batik cap, isen-isen, and symmetry tools for the native motif editor."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk

from batikcraft_studio.application import BatikProjectSession, CapIsenError
from batikcraft_studio.imaging.isen import (
    ISEN_LABELS,
    SUSUN_LABELS,
    IsenError,
    symmetry_placements,
)

from .shape_editor import ShapeEditorWorkspaceView
from .theme import COLORS
from .tooltip import ToolTip
from .widgets import icon_button

_ISEN_BY_LABEL = {label: key for key, label in ISEN_LABELS.items()}
_SUSUN_BY_LABEL = {label: key for key, label in SUSUN_LABELS.items()}
_PALET_BATIK = (
    ("Soga", "#8B5A2B"),
    ("Indigo", "#243B66"),
    ("Gading", "#E8D8B8"),
    ("Mengkudu", "#8F3D36"),
    ("Hitam", "#1C1917"),
)


class BatikEditorWorkspaceView(ShapeEditorWorkspaceView):
    """Add cap motif, isen presets, and batik-oriented symmetry arrangements."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        parent = args[0] if args else kwargs["parent"]
        self.isen_label_value = tk.StringVar(master=parent, value=ISEN_LABELS["cecek"])
        self.cap_size_value = tk.DoubleVar(master=parent, value=72.0)
        self.cap_color_value = tk.StringVar(master=parent, value="#7A3E2A")
        self.susun_label_value = tk.StringVar(master=parent, value=SUSUN_LABELS["tunggal"])
        self._cap_press_point: tuple[float, float] | None = None
        self._cap_cursor_position: tuple[float, float] | None = None
        super().__init__(*args, **kwargs)
        self.canvas.bind("<Motion>", self._on_cap_cursor_motion, add="+")
        self.canvas.bind("<Leave>", self._on_cap_cursor_leave, add="+")
        for variable in (self.cap_size_value, self.isen_label_value, self.susun_label_value):
            variable.trace_add("write", lambda *_args: self._refresh_cap_preview())

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        toolbox = ttk.Frame(self, style="Toolbar.TFrame", width=42, padding=(3, 4))
        toolbox.grid(row=0, column=0, sticky="ns")
        toolbox.grid_propagate(False)
        toolbox.columnconfigure(0, weight=1)
        tools = (
            ("select", "select", "Select and move objects (V)", self.activate_select_tool),
            ("brush", "editor", "Brush tool (B)", self.activate_brush_tool),
            ("eraser", "delete", "Eraser tool (E)", self.activate_eraser_tool),
            ("cap_isen", "batikification", "Cap Isen (C)", self.activate_cap_isen_tool),
            ("line", "line_tool", "Line tool (L)", lambda: self._activate_shape_tool("line")),
            (
                "rectangle",
                "rectangle_tool",
                "Rectangle tool (R)",
                lambda: self._activate_shape_tool("rectangle"),
            ),
            (
                "ellipse",
                "ellipse_tool",
                "Ellipse tool (O)",
                lambda: self._activate_shape_tool("ellipse"),
            ),
            (
                "polygon",
                "polygon_tool",
                "Polygon tool (P)",
                lambda: self._activate_shape_tool("polygon"),
            ),
        )
        for row, (key, icon, tooltip, command) in enumerate(tools):
            button = icon_button(
                toolbox,
                icon=icon,
                tooltip=tooltip,
                command=command,
                style="ToolActive.TButton" if key == "select" else "Tool.TButton",
                size=20,
            )
            button.grid(row=row, column=0, sticky="ew", pady=1)
            self._tool_buttons[key] = button
        icon_button(
            toolbox,
            icon="import",
            tooltip="Import image (Ctrl+I)",
            command=self.import_image_dialog,
            size=20,
        ).grid(row=len(tools), column=0, sticky="ew", pady=(8, 1))

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.grid(row=0, column=1, sticky="nsew")
        canvas_shell = ttk.Frame(body, style="App.TFrame")
        canvas_shell.columnconfigure(0, weight=1)
        canvas_shell.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            canvas_shell,
            background=COLORS["canvas"],
            highlightthickness=0,
            borderwidth=0,
            cursor="arrow",
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self._schedule_render())
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        ttk.Label(
            canvas_shell,
            textvariable=self.canvas_caption,
            style="Status.TLabel",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew")
        body.add(canvas_shell, weight=5)

        dock = ttk.Frame(body, style="Dock.TFrame", width=292)
        dock.grid_propagate(False)
        dock.columnconfigure(0, weight=1)
        dock.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(dock)
        notebook.grid(row=0, column=0, sticky="nsew")
        self._add_dock_tabs(notebook)
        body.add(dock, weight=1)

    def _add_dock_tabs(self, notebook: ttk.Notebook) -> None:
        super()._add_dock_tabs(notebook)
        batik_tab = ttk.Frame(notebook, style="Dock.TFrame", padding=(10, 10))
        batik_tab.columnconfigure(0, weight=1)
        self._build_batik_panel(batik_tab)
        notebook.add(batik_tab, text="Batik")

    def _build_layer_panel(self, parent: ttk.Frame) -> None:
        super()._build_layer_panel(parent)
        submenu_path = self._layer_context_menu.entrycget(0, "menu")
        new_layer_menu = self._layer_context_menu.nametowidget(submenu_path)
        isen_menu = tk.Menu(new_layer_menu, tearoff=False)
        for isen_type, label in ISEN_LABELS.items():
            isen_menu.add_command(
                label=label,
                command=lambda kind=isen_type: self._new_isen_layer(kind),
            )
        new_layer_menu.add_separator()
        new_layer_menu.add_cascade(label="Isen-Isen", menu=isen_menu)

    def _build_batik_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Cap Motif & Isen-Isen", style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            sticky="ew",
        )
        ttk.Label(
            parent,
            text="Pilih isen, pola susun, lalu klik kain untuk melakukan pengecapan.",
            style="Muted.TLabel",
            wraplength=250,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(parent, text="Jenis isen", style="Muted.TLabel").grid(
            row=2,
            column=0,
            sticky="w",
        )
        ttk.Combobox(
            parent,
            textvariable=self.isen_label_value,
            values=tuple(ISEN_LABELS.values()),
            state="readonly",
        ).grid(row=3, column=0, sticky="ew", pady=(3, 9))

        ttk.Label(parent, text="Ukuran cap", style="Muted.TLabel").grid(
            row=4,
            column=0,
            sticky="w",
        )
        size_row = ttk.Frame(parent, style="Dock.TFrame")
        size_row.grid(row=5, column=0, sticky="ew", pady=(3, 9))
        size_row.columnconfigure(0, weight=1)
        ttk.Scale(
            size_row,
            from_=8,
            to=512,
            variable=self.cap_size_value,
            orient=tk.HORIZONTAL,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Spinbox(
            size_row,
            from_=8,
            to=1024,
            increment=1,
            textvariable=self.cap_size_value,
            width=7,
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(parent, text="Warna isen", style="Muted.TLabel").grid(
            row=6,
            column=0,
            sticky="w",
        )
        self.cap_color_swatch = self._color_swatch(
            parent,
            self.cap_color_value,
            self._choose_cap_color,
            "Pilih warna isen",
        )
        self.cap_color_swatch.grid(row=7, column=0, sticky="ew", pady=(3, 7))

        ttk.Label(parent, text="Palet batik", style="Muted.TLabel").grid(
            row=8,
            column=0,
            sticky="w",
        )
        palette = ttk.Frame(parent, style="Dock.TFrame")
        palette.grid(row=9, column=0, sticky="ew", pady=(3, 10))
        for index, (name, color) in enumerate(_PALET_BATIK):
            palette.columnconfigure(index, weight=1)
            button = tk.Button(
                palette,
                background=color,
                activebackground=color,
                relief=tk.FLAT,
                borderwidth=1,
                width=2,
                command=lambda value=color, label=name: self._set_cap_color(value, label),
                cursor="hand2",
            )
            button.grid(row=0, column=index, sticky="ew", padx=(0, 3) if index < 4 else 0)
            ToolTip(button, name)

        ttk.Label(parent, text="Pola susun", style="Muted.TLabel").grid(
            row=10,
            column=0,
            sticky="w",
        )
        ttk.Combobox(
            parent,
            textvariable=self.susun_label_value,
            values=tuple(SUSUN_LABELS.values()),
            state="readonly",
        ).grid(row=11, column=0, sticky="ew", pady=(3, 10))

        icon_button(
            parent,
            icon="batikification",
            tooltip="Cap isen di tengah kain",
            command=self.cap_isen_di_tengah,
            size=20,
        ).grid(row=12, column=0, sticky="e")
        ttk.Label(
            parent,
            text=(
                "C  Cap Isen\n"
                "Cermin dan putar dihitung dari pusat kain\n"
                "Satu pengecapan = satu langkah Undo"
            ),
            style="Muted.TLabel",
            justify="left",
        ).grid(row=13, column=0, sticky="w", pady=(12, 0))
        self.bind_all("<Key-c>", self._activate_cap_shortcut)

    def activate_cap_isen_tool(self) -> None:
        self._set_active_tool("cap_isen", "Cap Isen aktif — klik kain untuk mengecap motif.")

    def _activate_cap_shortcut(self, event: tk.Event[tk.Misc]) -> str | None:
        if self._event_targets_text_input(event):
            return None
        self.activate_cap_isen_tool()
        return "break"

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "cap_isen":
            super()._on_canvas_press(event)
            return
        self._cap_press_point = self._project_point(event.x, event.y)

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "cap_isen":
            super()._on_canvas_drag(event)

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "cap_isen":
            super()._on_canvas_release(event)
            return
        point = self._project_point(event.x, event.y) or self._cap_press_point
        self._cap_press_point = None
        if point is not None:
            self._cap_at(point)

    def cap_isen_di_tengah(self) -> None:
        project = self.session.project
        if project is None:
            self.set_status("Buat atau buka proyek sebelum menggunakan Cap Isen.")
            return
        self._cap_at((project.canvas.width / 2, project.canvas.height / 2))

    def _cap_at(self, point: tuple[float, float]) -> None:
        try:
            layers = self._batik_session.cap_isen(
                self._isen_type(),
                point,
                ukuran=float(self.cap_size_value.get()),
                warna=self.cap_color_value.get(),
                susun=self._susun_type(),
            )
        except (CapIsenError, IsenError, ValueError) as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(f"Pengecapan selesai: {len(layers)} lapis {ISEN_LABELS[self._isen_type()]}")

    def _new_isen_layer(self, isen_type: str) -> None:
        if not self.session.has_project:
            self.set_status("Buat atau buka proyek sebelum menambah isen-isen.")
            return
        try:
            layers = self._batik_session.cap_isen_di_tengah(
                isen_type,
                ukuran=float(self.cap_size_value.get()),
                warna=self.cap_color_value.get(),
                susun="tunggal",
            )
        except (CapIsenError, ValueError) as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(f"Lapis isen dibuat: {layers[0].name}")

    def _choose_cap_color(self) -> None:
        _rgb, selected = colorchooser.askcolor(
            color=self.cap_color_value.get(),
            parent=self.winfo_toplevel(),
            title="Pilih Warna Isen",
        )
        if selected:
            self._set_cap_color(selected.upper(), "Warna pilihan")

    def _set_cap_color(self, color: str, label: str) -> None:
        self.cap_color_value.set(color.upper())
        self.cap_color_swatch.configure(background=color, activebackground=color)
        self.set_status(f"Palet {label} dipilih.")

    def _on_cap_cursor_motion(self, event: tk.Event[tk.Canvas]) -> None:
        self._cap_cursor_position = (event.x, event.y)
        self._refresh_cap_preview()

    def _on_cap_cursor_leave(self, _event: tk.Event[tk.Canvas]) -> None:
        self._cap_cursor_position = None
        self.canvas.delete("cap-isen-preview")

    def _refresh_cap_preview(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("cap-isen-preview")
        if self._active_tool != "cap_isen" or self._cap_cursor_position is None:
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
            radius = max(2.0, float(self.cap_size_value.get()) * self._preview_scale / 2)
        except (IsenError, ValueError, tk.TclError):
            return
        for placement in placements:
            x = self._preview_left + placement.x * self._preview_scale
            y = self._preview_top + placement.y * self._preview_scale
            self.canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                outline="#FFFFFF",
                width=3,
                tags="cap-isen-preview",
            )
            self.canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                outline=COLORS["accent"],
                width=1,
                tags="cap-isen-preview",
            )
        self.canvas.tag_raise("cap-isen-preview")

    def _refresh_brush_cursor(self) -> None:
        if not hasattr(self, "canvas"):
            return
        if self._active_tool not in {"brush", "eraser"}:
            self.canvas.delete("brush-cursor")
            return
        super()._refresh_brush_cursor()

    def _set_active_tool(self, tool: str, status: str) -> None:
        super()._set_active_tool(tool, status)
        self.canvas.delete("cap-isen-preview")
        self._refresh_cap_preview()

    def _isen_type(self) -> str:
        return _ISEN_BY_LABEL.get(self.isen_label_value.get(), "cecek")

    def _susun_type(self) -> str:
        return _SUSUN_BY_LABEL.get(self.susun_label_value.get(), "tunggal")

    @property
    def _batik_session(self) -> BatikProjectSession:
        if not isinstance(self.session, BatikProjectSession):
            raise RuntimeError("Editor memerlukan project session yang mendukung Cap Isen.")
        return self.session
