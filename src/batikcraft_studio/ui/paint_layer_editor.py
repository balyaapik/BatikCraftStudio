"""Native paint-enabled layer editor for brush and eraser workflows."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import colorchooser, ttk

from batikcraft_studio.application import PaintLayerError, PaintProjectSession, ProjectSessionError
from batikcraft_studio.domain import LayerKind, ProjectValidationError
from batikcraft_studio.imaging.paint import PaintStrokeError

from .native_layer_editor import NativeLayerEditorWorkspaceView
from .theme import COLORS
from .tooltip import ToolTip
from .widgets import icon_button


class PaintLayerEditorWorkspaceView(NativeLayerEditorWorkspaceView):
    """Add full-canvas paint layers and one-history-entry brush strokes."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        parent = args[0] if args else kwargs["parent"]
        self._active_tool = "select"
        self._tool_buttons: dict[str, ttk.Button] = {}
        self.brush_size_value = tk.DoubleVar(master=parent, value=24.0)
        self.brush_color_value = tk.StringVar(master=parent, value="#7A3E2A")
        self._stroke_layer_id: str | None = None
        self._stroke_points: list[tuple[float, float]] = []
        self._stroke_last_screen: tuple[float, float] | None = None
        super().__init__(*args, **kwargs)

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        toolbox = ttk.Frame(self, style="Toolbar.TFrame", width=42, padding=(3, 4))
        toolbox.grid(row=0, column=0, sticky="ns")
        toolbox.grid_propagate(False)
        toolbox.columnconfigure(0, weight=1)

        tools = (
            ("select", "select", "Select and move objects", self.activate_select_tool),
            ("brush", "editor", "Brush tool", self.activate_brush_tool),
            ("eraser", "delete", "Eraser tool", self.activate_eraser_tool),
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

        layers_tab = ttk.Frame(notebook, style="Dock.TFrame", padding=(8, 8))
        layers_tab.columnconfigure(0, weight=1)
        layers_tab.rowconfigure(1, weight=1)
        self._build_layer_panel(layers_tab)
        notebook.add(layers_tab, text="Layers")

        transform_tab = ttk.Frame(notebook, style="Dock.TFrame", padding=(10, 10))
        transform_tab.columnconfigure(0, weight=1)
        self._build_transform_panel(transform_tab)
        notebook.add(transform_tab, text="Transform")

        brush_tab = ttk.Frame(notebook, style="Dock.TFrame", padding=(10, 10))
        brush_tab.columnconfigure(0, weight=1)
        self._build_brush_panel(brush_tab)
        notebook.add(brush_tab, text="Brush")
        body.add(dock, weight=1)

    def _build_brush_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Paint tools", style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            sticky="ew",
        )
        ttk.Label(
            parent,
            text="Strokes are stored on transparent full-canvas paint layers.",
            style="Muted.TLabel",
            wraplength=250,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(parent, text="Brush size", style="Muted.TLabel").grid(
            row=2,
            column=0,
            sticky="w",
        )
        size_row = ttk.Frame(parent, style="Dock.TFrame")
        size_row.grid(row=3, column=0, sticky="ew", pady=(3, 10))
        size_row.columnconfigure(0, weight=1)
        ttk.Scale(
            size_row,
            from_=1,
            to=256,
            variable=self.brush_size_value,
            orient=tk.HORIZONTAL,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Spinbox(
            size_row,
            from_=1,
            to=256,
            increment=1,
            textvariable=self.brush_size_value,
            width=6,
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(parent, text="Brush color", style="Muted.TLabel").grid(
            row=4,
            column=0,
            sticky="w",
        )
        self.color_swatch = tk.Button(
            parent,
            background=self.brush_color_value.get(),
            activebackground=self.brush_color_value.get(),
            relief=tk.FLAT,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=COLORS["line"],
            height=2,
            command=self.choose_brush_color,
            cursor="hand2",
        )
        self.color_swatch.grid(row=5, column=0, sticky="ew", pady=(3, 10))
        ToolTip(self.color_swatch, "Choose brush color")

        ttk.Label(
            parent,
            text="Brush shortcut: B\nEraser shortcut: E\nSelect shortcut: V",
            style="Muted.TLabel",
            justify="left",
        ).grid(row=6, column=0, sticky="w", pady=(8, 0))

        self.bind_all("<Key-b>", lambda _event: self.activate_brush_tool())
        self.bind_all("<Key-e>", lambda _event: self.activate_eraser_tool())
        self.bind_all("<Key-v>", lambda _event: self.activate_select_tool())

    def activate_select_tool(self) -> None:
        self._set_active_tool("select", "Select tool active")

    def activate_brush_tool(self) -> None:
        self._set_active_tool("brush", "Brush tool active")

    def activate_eraser_tool(self) -> None:
        self._set_active_tool("eraser", "Eraser tool active")

    def choose_brush_color(self) -> None:
        _rgb, selected = colorchooser.askcolor(
            color=self.brush_color_value.get(),
            parent=self.winfo_toplevel(),
            title="Choose Brush Color",
        )
        if not selected:
            return
        self.brush_color_value.set(selected.upper())
        self.color_swatch.configure(background=selected, activebackground=selected)

    def _set_active_tool(self, tool: str, status: str) -> None:
        self._active_tool = tool
        self._clear_paint_stroke()
        for key, button in self._tool_buttons.items():
            button.configure(style="ToolActive.TButton" if key == tool else "Tool.TButton")
        self.canvas.configure(cursor="arrow" if tool == "select" else "crosshair")
        self.set_status(status)

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool == "select":
            super()._on_canvas_press(event)
            return
        point = self._project_point(event.x, event.y)
        project = self.session.project
        if project is None or point is None:
            self.set_status("Create or open a project before painting.")
            return
        if not (0 <= point[0] < project.canvas.width and 0 <= point[1] < project.canvas.height):
            return
        try:
            layer = self._paint_session.ensure_active_paint_layer()
        except (ProjectSessionError, ProjectValidationError, PaintStrokeError) as exc:
            self.set_status(str(exc))
            return
        self._stroke_layer_id = layer.layer_id
        self._stroke_points = [point]
        self._stroke_last_screen = (event.x, event.y)
        self.canvas.delete("paint-preview")
        self._draw_preview_dot(event.x, event.y)

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool == "select":
            super()._on_canvas_drag(event)
            return
        if self._stroke_layer_id is None or self._stroke_last_screen is None:
            return
        point = self._project_point(event.x, event.y)
        if point is None:
            return
        previous_x, previous_y = self._stroke_last_screen
        if math.hypot(event.x - previous_x, event.y - previous_y) < 1.5:
            return
        self._stroke_points.append(point)
        self._draw_preview_line(previous_x, previous_y, event.x, event.y)
        self._stroke_last_screen = (event.x, event.y)

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool == "select":
            super()._on_canvas_release(event)
            return
        if self._stroke_layer_id is None:
            self._clear_paint_stroke()
            return
        point = self._project_point(event.x, event.y)
        if point is not None and (not self._stroke_points or point != self._stroke_points[-1]):
            self._stroke_points.append(point)
        try:
            self._paint_session.apply_paint_stroke(
                self._stroke_layer_id,
                points=tuple(self._stroke_points),
                brush_size=float(self.brush_size_value.get()),
                color=self.brush_color_value.get(),
                erase=self._active_tool == "eraser",
            )
        except (PaintLayerError, ProjectSessionError, PaintStrokeError, ValueError) as exc:
            self.set_status(str(exc))
            self._clear_paint_stroke()
            self._schedule_render()
            return
        tool_label = "Eraser" if self._active_tool == "eraser" else "Brush"
        self._clear_paint_stroke()
        self.refresh_context()
        self.set_status(f"{tool_label} stroke committed.")

    def _project_point(self, screen_x: float, screen_y: float) -> tuple[float, float] | None:
        if self._preview_scale <= 0:
            return None
        return (
            (screen_x - self._preview_left) / self._preview_scale,
            (screen_y - self._preview_top) / self._preview_scale,
        )

    def _draw_preview_dot(self, x: float, y: float) -> None:
        radius = self._preview_width() / 2
        options = self._preview_options()
        self.canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            tags="paint-preview",
            **options,
        )

    def _draw_preview_line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        options = self._preview_options()
        self.canvas.create_line(
            x1,
            y1,
            x2,
            y2,
            width=self._preview_width(),
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
            tags="paint-preview",
            **options,
        )

    def _preview_options(self) -> dict[str, object]:
        if self._active_tool == "eraser":
            return {"fill": "#FFFFFF", "stipple": "gray50", "outline": ""}
        return {"fill": self.brush_color_value.get(), "outline": ""}

    def _preview_width(self) -> int:
        return max(1, round(float(self.brush_size_value.get()) * self._preview_scale))

    def _clear_paint_stroke(self) -> None:
        self._stroke_layer_id = None
        self._stroke_points = []
        self._stroke_last_screen = None
        if hasattr(self, "canvas"):
            self.canvas.delete("paint-preview")

    @property
    def _paint_session(self) -> PaintProjectSession:
        if not isinstance(self.session, PaintProjectSession):
            raise RuntimeError("The editor requires a paint-enabled project session.")
        return self.session
