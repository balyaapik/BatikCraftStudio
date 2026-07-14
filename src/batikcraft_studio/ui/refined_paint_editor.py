"""Refined native brush controls layered on top of the Milestone 3A editor."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from batikcraft_studio.application import PaintLayerError, ProjectSessionError
from batikcraft_studio.domain import ProjectValidationError
from batikcraft_studio.imaging.paint import PaintStrokeError

from .paint_layer_editor import PaintLayerEditorWorkspaceView
from .theme import COLORS
from .tooltip import ToolTip

BRUSH_SIZE_PRESETS = (4, 12, 24, 48, 96)
BRUSH_SIZE_STEPS = (1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256)


class RefinedPaintLayerEditorWorkspaceView(PaintLayerEditorWorkspaceView):
    """Add smoothing, opacity, hardness, presets, and a circular brush cursor."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        parent = args[0] if args else kwargs["parent"]
        self.brush_opacity_value = tk.DoubleVar(master=parent, value=100.0)
        self.brush_hardness_value = tk.DoubleVar(master=parent, value=82.0)
        self.brush_smoothing_value = tk.DoubleVar(master=parent, value=45.0)
        self._brush_cursor_position: tuple[float, float] | None = None
        super().__init__(*args, **kwargs)

        self.canvas.bind("<Motion>", self._on_brush_cursor_motion, add="+")
        self.canvas.bind("<Leave>", self._on_brush_cursor_leave, add="+")
        for variable in (
            self.brush_size_value,
            self.brush_opacity_value,
            self.brush_hardness_value,
        ):
            variable.trace_add("write", lambda *_args: self._refresh_brush_cursor())

    def _build_brush_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Brush controls", style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            sticky="ew",
        )
        ttk.Label(
            parent,
            text="Refined raster strokes remain editable through paint-layer history.",
            style="Muted.TLabel",
            wraplength=250,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 12))

        self._build_slider_row(
            parent,
            row=2,
            label="Size",
            variable=self.brush_size_value,
            start=1,
            end=256,
            increment=1,
        )

        ttk.Label(parent, text="Size presets", style="Muted.TLabel").grid(
            row=4,
            column=0,
            sticky="w",
            pady=(2, 3),
        )
        presets = ttk.Frame(parent, style="Dock.TFrame")
        presets.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        for index, size in enumerate(BRUSH_SIZE_PRESETS):
            presets.columnconfigure(index, weight=1)
            button = ttk.Button(
                presets,
                text=str(size),
                style="Secondary.TButton",
                command=lambda value=size: self._set_brush_size(value),
                width=3,
            )
            button.grid(row=0, column=index, sticky="ew", padx=(0, 3) if index < 4 else 0)
            ToolTip(button, f"Set brush size to {size}px")

        self._build_slider_row(
            parent,
            row=6,
            label="Opacity (%)",
            variable=self.brush_opacity_value,
            start=1,
            end=100,
            increment=1,
        )
        self._build_slider_row(
            parent,
            row=8,
            label="Hardness (%)",
            variable=self.brush_hardness_value,
            start=0,
            end=100,
            increment=1,
        )
        self._build_slider_row(
            parent,
            row=10,
            label="Smoothing (%)",
            variable=self.brush_smoothing_value,
            start=0,
            end=100,
            increment=1,
        )

        ttk.Label(parent, text="Brush color", style="Muted.TLabel").grid(
            row=12,
            column=0,
            sticky="w",
            pady=(2, 0),
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
        self.color_swatch.grid(row=13, column=0, sticky="ew", pady=(3, 10))
        ToolTip(self.color_swatch, "Choose brush color")

        ttk.Label(
            parent,
            text=(
                "B  Brush    E  Eraser    V  Select\n"
                "[  Smaller brush    ]  Larger brush"
            ),
            style="Muted.TLabel",
            justify="left",
        ).grid(row=14, column=0, sticky="w", pady=(8, 0))

        self.bind_all("<Key-b>", lambda event: self._activate_tool_shortcut(event, "brush"))
        self.bind_all("<Key-e>", lambda event: self._activate_tool_shortcut(event, "eraser"))
        self.bind_all("<Key-v>", lambda event: self._activate_tool_shortcut(event, "select"))
        self.bind_all("<Key-bracketleft>", lambda event: self._adjust_brush_size(event, -1))
        self.bind_all("<Key-bracketright>", lambda event: self._adjust_brush_size(event, 1))

    def _build_slider_row(
        self,
        parent: ttk.Frame,
        *,
        row: int,
        label: str,
        variable: tk.DoubleVar,
        start: float,
        end: float,
        increment: float,
    ) -> None:
        ttk.Label(parent, text=label, style="Muted.TLabel").grid(
            row=row,
            column=0,
            sticky="w",
        )
        controls = ttk.Frame(parent, style="Dock.TFrame")
        controls.grid(row=row + 1, column=0, sticky="ew", pady=(3, 10))
        controls.columnconfigure(0, weight=1)
        ttk.Scale(
            controls,
            from_=start,
            to=end,
            variable=variable,
            orient=tk.HORIZONTAL,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Spinbox(
            controls,
            from_=start,
            to=end,
            increment=increment,
            textvariable=variable,
            width=6,
        ).grid(row=0, column=1, padx=(8, 0))

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
                opacity=self._percentage(self.brush_opacity_value),
                hardness=self._percentage(self.brush_hardness_value),
                smoothing=self._percentage(self.brush_smoothing_value),
            )
        except (PaintLayerError, ProjectSessionError, PaintStrokeError, ValueError) as exc:
            self.set_status(str(exc))
            self._clear_paint_stroke()
            self._schedule_render()
            return

        tool_label = "Eraser" if self._active_tool == "eraser" else "Brush"
        self._clear_paint_stroke()
        self.refresh_context()
        self.set_status(
            f"{tool_label} stroke committed at {round(self.brush_opacity_value.get())}% opacity."
        )

    def _preview_style(self) -> tuple[str, str]:
        fill = "#FFFFFF" if self._active_tool == "eraser" else self.brush_color_value.get()
        opacity = self._percentage(self.brush_opacity_value)
        if opacity >= 0.88:
            stipple = ""
        elif opacity >= 0.62:
            stipple = "gray75"
        elif opacity >= 0.38:
            stipple = "gray50"
        elif opacity >= 0.18:
            stipple = "gray25"
        else:
            stipple = "gray12"
        return fill, stipple

    def _set_active_tool(self, tool: str, status: str) -> None:
        super()._set_active_tool(tool, status)
        self.canvas.delete("brush-cursor")
        self._refresh_brush_cursor()

    def _set_brush_size(self, value: int) -> None:
        self.brush_size_value.set(float(value))
        self.set_status(f"Brush size set to {value}px.")

    def _adjust_brush_size(self, event: tk.Event[tk.Misc], direction: int) -> str | None:
        if self._event_targets_text_input(event):
            return None
        current = float(self.brush_size_value.get())
        if direction < 0:
            candidates = [value for value in BRUSH_SIZE_STEPS if value < current]
            target = candidates[-1] if candidates else BRUSH_SIZE_STEPS[0]
        else:
            candidates = [value for value in BRUSH_SIZE_STEPS if value > current]
            target = candidates[0] if candidates else BRUSH_SIZE_STEPS[-1]
        self._set_brush_size(target)
        return "break"

    def _on_brush_cursor_motion(self, event: tk.Event[tk.Canvas]) -> None:
        self._brush_cursor_position = (event.x, event.y)
        self._refresh_brush_cursor()

    def _on_brush_cursor_leave(self, _event: tk.Event[tk.Canvas]) -> None:
        self._brush_cursor_position = None
        self.canvas.delete("brush-cursor")

    def _refresh_brush_cursor(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("brush-cursor")
        if self._active_tool == "select" or self._brush_cursor_position is None:
            return

        x, y = self._brush_cursor_position
        point = self._project_point(x, y)
        project = self.session.project
        if (
            point is None
            or project is None
            or not (0 <= point[0] < project.canvas.width and 0 <= point[1] < project.canvas.height)
        ):
            return

        radius = self._preview_width() / 2
        bounds = (x - radius, y - radius, x + radius, y + radius)
        self.canvas.create_oval(
            *bounds,
            outline="#FFFFFF",
            width=3,
            tags="brush-cursor",
        )
        self.canvas.create_oval(
            *bounds,
            outline=COLORS["warning"] if self._active_tool == "eraser" else COLORS["ink"],
            width=1,
            tags="brush-cursor",
        )
        self.canvas.tag_raise("brush-cursor")

    @staticmethod
    def _percentage(variable: tk.DoubleVar) -> float:
        return min(1.0, max(0.0, float(variable.get()) / 100.0))

    @staticmethod
    def _event_targets_text_input(event: tk.Event[tk.Misc]) -> bool:
        return event.widget.winfo_class() in {"Entry", "TEntry", "Spinbox", "TSpinbox"}
