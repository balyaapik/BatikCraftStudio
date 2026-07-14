"""Native shape and line tools with a Layers right-click context menu."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import colorchooser, ttk

from batikcraft_studio.application import ShapeLayerError, ShapeProjectSession
from batikcraft_studio.domain import LayerKind
from batikcraft_studio.imaging.shape import ShapeError, build_shape_geometry

from .refined_paint_editor import RefinedPaintLayerEditorWorkspaceView
from .theme import COLORS
from .tooltip import ToolTip
from .widgets import icon_button

_SHAPE_TOOLS = ("line", "rectangle", "ellipse", "polygon")
_SHIFT_MASK = 0x0001
_ALT_MASKS = (0x0008, 0x20000)


class ShapeEditorWorkspaceView(RefinedPaintLayerEditorWorkspaceView):
    """Add non-destructive shapes and a native layer context menu."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        parent = args[0] if args else kwargs["parent"]
        self.shape_fill_enabled = tk.BooleanVar(master=parent, value=True)
        self.shape_stroke_enabled = tk.BooleanVar(master=parent, value=True)
        self.shape_fill_color = tk.StringVar(master=parent, value="#D9A566")
        self.shape_stroke_color = tk.StringVar(master=parent, value="#273043")
        self.shape_stroke_width = tk.DoubleVar(master=parent, value=4.0)
        self.shape_polygon_sides = tk.IntVar(master=parent, value=6)
        self.shape_width_value = tk.DoubleVar(master=parent, value=240.0)
        self.shape_height_value = tk.DoubleVar(master=parent, value=160.0)
        self.shape_type_text = tk.StringVar(master=parent, value="No shape selected")
        self._shape_start: tuple[float, float] | None = None
        self._shape_last: tuple[float, float] | None = None
        self._shape_widgets_ready = False
        super().__init__(*args, **kwargs)

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

        shape_tab = ttk.Frame(notebook, style="Dock.TFrame", padding=(10, 10))
        shape_tab.columnconfigure(0, weight=1)
        self._build_shape_panel(shape_tab)
        notebook.add(shape_tab, text="Shape")

    def _build_layer_panel(self, parent: ttk.Frame) -> None:
        super()._build_layer_panel(parent)
        self._layer_context_menu = tk.Menu(self, tearoff=False)
        new_layer_menu = tk.Menu(self._layer_context_menu, tearoff=False)
        new_layer_menu.add_command(label="Paint Layer", command=self._new_paint_layer)
        new_layer_menu.add_separator()
        for shape_type in _SHAPE_TOOLS:
            new_layer_menu.add_command(
                label=shape_type.title(),
                command=lambda kind=shape_type: self._new_default_shape(kind),
            )
        self._layer_context_menu.add_cascade(label="New Layer", menu=new_layer_menu)
        self._layer_context_menu.add_separator()
        self._layer_context_menu.add_command(
            label="Duplicate Layer",
            command=self.duplicate_active,
        )
        self._layer_context_menu.add_command(
            label="Delete Layer",
            command=self.delete_active,
        )
        self._layer_context_menu.add_separator()
        self._layer_context_menu.add_command(
            label="Hide Layer",
            command=self.toggle_visibility,
        )
        self._layer_context_menu.add_command(
            label="Lock Layer",
            command=self.toggle_lock,
        )
        self.layer_list.bind("<Button-3>", self._show_layer_context_menu)

    def _build_shape_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Shape properties", style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            sticky="ew",
        )
        ttk.Label(
            parent,
            textvariable=self.shape_type_text,
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 10))
        self._build_shape_geometry_controls(parent)
        self._build_shape_color_controls(parent)
        self._build_shape_style_controls(parent)
        icon_button(
            parent,
            icon="apply",
            tooltip="Apply shape properties",
            command=self.apply_shape_properties,
            size=19,
        ).grid(row=6, column=0, sticky="e", pady=(10, 0))
        ttk.Label(
            parent,
            text=(
                "L Line   R Rectangle   O Ellipse   P Polygon\n"
                "Shift constrains   Alt draws from center"
            ),
            style="Muted.TLabel",
            justify="left",
        ).grid(row=7, column=0, sticky="w", pady=(12, 0))
        for sequence, tool in (
            ("<Key-l>", "line"),
            ("<Key-r>", "rectangle"),
            ("<Key-o>", "ellipse"),
            ("<Key-p>", "polygon"),
        ):
            self.bind_all(
                sequence,
                lambda event, kind=tool: self._activate_shape_shortcut(event, kind),
            )
        self._shape_widgets_ready = True

    def _build_shape_geometry_controls(self, parent: ttk.Frame) -> None:
        geometry = ttk.Frame(parent, style="Dock.TFrame")
        geometry.grid(row=2, column=0, sticky="ew")
        geometry.columnconfigure(1, weight=1)
        for row, (label, variable) in enumerate(
            (("Width", self.shape_width_value), ("Height", self.shape_height_value))
        ):
            ttk.Label(geometry, text=label, style="Muted.TLabel").grid(
                row=row,
                column=0,
                sticky="w",
                pady=3,
            )
            ttk.Spinbox(
                geometry,
                from_=1,
                to=16384,
                increment=1,
                textvariable=variable,
                width=8,
            ).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)

    def _build_shape_color_controls(self, parent: ttk.Frame) -> None:
        fill_row = ttk.Frame(parent, style="Dock.TFrame")
        fill_row.grid(row=3, column=0, sticky="ew", pady=(10, 4))
        fill_row.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            fill_row,
            text="Fill",
            variable=self.shape_fill_enabled,
        ).grid(row=0, column=0, sticky="w")
        self.fill_swatch = self._color_swatch(
            fill_row,
            self.shape_fill_color,
            self._choose_shape_fill,
            "Choose shape fill color",
        )
        self.fill_swatch.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        stroke_row = ttk.Frame(parent, style="Dock.TFrame")
        stroke_row.grid(row=4, column=0, sticky="ew", pady=4)
        stroke_row.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            stroke_row,
            text="Stroke",
            variable=self.shape_stroke_enabled,
        ).grid(row=0, column=0, sticky="w")
        self.stroke_swatch = self._color_swatch(
            stroke_row,
            self.shape_stroke_color,
            self._choose_shape_stroke,
            "Choose shape stroke color",
        )
        self.stroke_swatch.grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _build_shape_style_controls(self, parent: ttk.Frame) -> None:
        style_grid = ttk.Frame(parent, style="Dock.TFrame")
        style_grid.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        style_grid.columnconfigure(1, weight=1)
        fields = (
            ("Stroke width", self.shape_stroke_width, 0.5, 128),
            ("Polygon sides", self.shape_polygon_sides, 3, 12),
        )
        for row, (label, variable, start, end) in enumerate(fields):
            ttk.Label(style_grid, text=label, style="Muted.TLabel").grid(
                row=row,
                column=0,
                sticky="w",
                pady=3,
            )
            ttk.Spinbox(
                style_grid,
                from_=start,
                to=end,
                increment=1,
                textvariable=variable,
                width=8,
            ).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)

    def _color_swatch(
        self,
        parent: tk.Misc,
        variable: tk.StringVar,
        command: object,
        tooltip: str,
    ) -> tk.Button:
        button = tk.Button(
            parent,
            background=variable.get(),
            activebackground=variable.get(),
            relief=tk.FLAT,
            borderwidth=1,
            height=1,
            command=command,
            cursor="hand2",
        )
        ToolTip(button, tooltip)
        return button

    def _show_layer_context_menu(self, event: tk.Event[tk.Listbox]) -> str:
        index = self.layer_list.nearest(event.y)
        bounds = self.layer_list.bbox(index)
        if bounds is not None and bounds[1] <= event.y <= bounds[1] + bounds[3]:
            self.layer_list.selection_clear(0, tk.END)
            self.layer_list.selection_set(index)
            self.layer_list.activate(index)
            self._on_layer_list_select(event)
        project_open = self.session.has_project
        active = self._active_layer()
        self._layer_context_menu.entryconfigure(
            0,
            state=tk.NORMAL if project_open else tk.DISABLED,
        )
        action_state = tk.NORMAL if active is not None else tk.DISABLED
        for menu_index in (2, 3, 5, 6):
            self._layer_context_menu.entryconfigure(menu_index, state=action_state)
        if active is not None:
            self._layer_context_menu.entryconfigure(
                5,
                label="Hide Layer" if active.visible else "Show Layer",
            )
            self._layer_context_menu.entryconfigure(
                6,
                label="Unlock Layer" if active.locked else "Lock Layer",
            )
        try:
            self._layer_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._layer_context_menu.grab_release()
        return "break"

    def _new_paint_layer(self) -> None:
        if not self.session.has_project:
            self.set_status("Create or open a project before adding a layer.")
            return
        layer = self._shape_session.create_paint_layer()
        self.refresh_context()
        self.set_status(f"Created layer: {layer.name}")

    def _new_default_shape(self, shape_type: str) -> None:
        if not self.session.has_project:
            self.set_status("Create or open a project before adding a layer.")
            return
        try:
            layer = self._shape_session.create_default_shape_layer(
                shape_type,
                **self._shape_style(shape_type),
            )
        except (ShapeLayerError, ValueError) as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(f"Created layer: {layer.name}")

    def apply_shape_properties(self) -> None:
        layer = self._active_layer()
        if layer is None or layer.kind is not LayerKind.SHAPE:
            self.set_status("Select a shape layer before applying shape properties.")
            return
        try:
            shape_type = str(layer.properties.get("shape_type"))
            self._shape_session.update_shape_layer(
                layer.layer_id,
                geometry_width=max(1.0, float(self.shape_width_value.get())),
                geometry_height=max(1.0, float(self.shape_height_value.get())),
                stroke_color=self.shape_stroke_color.get(),
                fill_color=self.shape_fill_color.get(),
                stroke_width=float(self.shape_stroke_width.get()),
                stroke_enabled=True
                if shape_type == "line"
                else bool(self.shape_stroke_enabled.get()),
                fill_enabled=False
                if shape_type == "line"
                else bool(self.shape_fill_enabled.get()),
                polygon_sides=int(self.shape_polygon_sides.get()),
            )
        except (ShapeLayerError, ValueError) as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(f"Updated shape: {layer.name}")

    def _refresh_transform_fields(self) -> None:
        super()._refresh_transform_fields()
        if not self._shape_widgets_ready:
            return
        layer = self._active_layer()
        if layer is None or layer.kind is not LayerKind.SHAPE:
            self.shape_type_text.set("No shape selected")
            return
        properties = layer.properties
        shape_type = str(properties.get("shape_type", "shape"))
        self.shape_type_text.set(f"Selected: {shape_type.title()}")
        self.shape_width_value.set(float(properties.get("geometry_width", 1.0)))
        self.shape_height_value.set(float(properties.get("geometry_height", 1.0)))
        self.shape_stroke_color.set(str(properties.get("stroke_color", "#273043")))
        self.shape_fill_color.set(str(properties.get("fill_color", "#D9A566")))
        self.shape_stroke_width.set(float(properties.get("stroke_width", 4.0)))
        self.shape_stroke_enabled.set(bool(properties.get("stroke_enabled", True)))
        self.shape_fill_enabled.set(bool(properties.get("fill_enabled", False)))
        self.shape_polygon_sides.set(int(properties.get("polygon_sides", 6)))
        self.stroke_swatch.configure(
            background=self.shape_stroke_color.get(),
            activebackground=self.shape_stroke_color.get(),
        )
        self.fill_swatch.configure(
            background=self.shape_fill_color.get(),
            activebackground=self.shape_fill_color.get(),
        )

    def _activate_shape_tool(self, shape_type: str) -> None:
        self._set_active_tool(shape_type, f"{shape_type.title()} tool active")

    def _activate_shape_shortcut(
        self,
        event: tk.Event[tk.Misc],
        shape_type: str,
    ) -> str | None:
        if self._event_targets_text_input(event):
            return None
        self._activate_shape_tool(shape_type)
        return "break"

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool not in _SHAPE_TOOLS:
            super()._on_canvas_press(event)
            return
        point = self._project_point(event.x, event.y)
        project = self.session.project
        if project is None or point is None:
            self.set_status("Create or open a project before drawing shapes.")
            return
        if not (0 <= point[0] < project.canvas.width and 0 <= point[1] < project.canvas.height):
            return
        self._shape_start = point
        self._shape_last = point
        self.canvas.delete("shape-preview")

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool not in _SHAPE_TOOLS:
            super()._on_canvas_drag(event)
            return
        if self._shape_start is None:
            return
        point = self._project_point(event.x, event.y)
        if point is None:
            return
        self._shape_last = point
        self._draw_shape_preview(point, event.state)

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool not in _SHAPE_TOOLS:
            super()._on_canvas_release(event)
            return
        if self._shape_start is None:
            self._clear_shape_preview()
            return
        point = self._project_point(event.x, event.y) or self._shape_last
        if point is None:
            self._clear_shape_preview()
            return
        try:
            layer = self._shape_session.create_shape_layer(
                self._active_tool,
                self._shape_start,
                point,
                constrain=self._shift_pressed(event.state),
                from_center=self._alt_pressed(event.state),
                **self._shape_style(self._active_tool),
            )
        except (ShapeLayerError, ShapeError, ValueError) as exc:
            self.set_status(str(exc))
            self._clear_shape_preview()
            return
        self._clear_shape_preview()
        self.refresh_context()
        self.set_status(f"Created shape: {layer.name}")

    def _draw_shape_preview(self, end: tuple[float, float], state: int) -> None:
        if self._shape_start is None:
            return
        try:
            geometry = build_shape_geometry(
                self._active_tool,
                self._shape_start,
                end,
                constrain=self._shift_pressed(state),
                from_center=self._alt_pressed(state),
                **self._shape_style(self._active_tool),
            )
        except ShapeError:
            return
        properties = geometry.properties
        geometry_width = float(properties["geometry_width"])
        geometry_height = float(properties["geometry_height"])
        left = self._preview_left + (
            geometry.center_x - geometry_width / 2
        ) * self._preview_scale
        top = self._preview_top + (
            geometry.center_y - geometry_height / 2
        ) * self._preview_scale
        right = self._preview_left + (
            geometry.center_x + geometry_width / 2
        ) * self._preview_scale
        bottom = self._preview_top + (
            geometry.center_y + geometry_height / 2
        ) * self._preview_scale
        stroke = self.shape_stroke_color.get()
        fill = self.shape_fill_color.get() if self.shape_fill_enabled.get() else ""
        width = max(1, round(float(self.shape_stroke_width.get()) * self._preview_scale))
        self.canvas.delete("shape-preview")
        self._create_shape_preview(
            properties,
            left,
            top,
            right,
            bottom,
            stroke,
            fill,
            width,
        )
        self.canvas.tag_raise("shape-preview")

    def _create_shape_preview(
        self,
        properties: object,
        left: float,
        top: float,
        right: float,
        bottom: float,
        stroke: str,
        fill: str,
        width: int,
    ) -> None:
        if not isinstance(properties, dict) and not hasattr(properties, "get"):
            return
        if self._active_tool == "line":
            orientation = str(properties["line_orientation"])
            points = self._line_preview_points(left, top, right, bottom, orientation)
            self.canvas.create_line(
                *points,
                fill=stroke,
                width=width,
                tags="shape-preview",
            )
            return
        common = {
            "fill": fill,
            "outline": stroke if self.shape_stroke_enabled.get() else "",
            "width": width,
            "stipple": "gray25" if fill else "",
            "tags": "shape-preview",
        }
        if self._active_tool == "rectangle":
            self.canvas.create_rectangle(left, top, right, bottom, **common)
        elif self._active_tool == "ellipse":
            self.canvas.create_oval(left, top, right, bottom, **common)
        else:
            points = self._polygon_preview_points(
                left,
                top,
                right,
                bottom,
                int(self.shape_polygon_sides.get()),
            )
            self.canvas.create_polygon(*points, **common)

    def _shape_style(self, shape_type: str) -> dict[str, object]:
        line = shape_type == "line"
        return {
            "stroke_color": self.shape_stroke_color.get(),
            "fill_color": self.shape_fill_color.get(),
            "stroke_width": float(self.shape_stroke_width.get()),
            "stroke_enabled": True if line else bool(self.shape_stroke_enabled.get()),
            "fill_enabled": False if line else bool(self.shape_fill_enabled.get()),
            "polygon_sides": int(self.shape_polygon_sides.get()),
        }

    def _choose_shape_fill(self) -> None:
        _rgb, selected = colorchooser.askcolor(
            color=self.shape_fill_color.get(),
            parent=self.winfo_toplevel(),
            title="Choose Shape Fill",
        )
        if selected:
            self.shape_fill_color.set(selected.upper())
            self.fill_swatch.configure(background=selected, activebackground=selected)

    def _choose_shape_stroke(self) -> None:
        _rgb, selected = colorchooser.askcolor(
            color=self.shape_stroke_color.get(),
            parent=self.winfo_toplevel(),
            title="Choose Shape Stroke",
        )
        if selected:
            self.shape_stroke_color.set(selected.upper())
            self.stroke_swatch.configure(background=selected, activebackground=selected)

    def _set_active_tool(self, tool: str, status: str) -> None:
        super()._set_active_tool(tool, status)
        if tool in _SHAPE_TOOLS:
            self.canvas.delete("brush-cursor")
            self.canvas.configure(cursor="crosshair")
        self._clear_shape_preview()

    def _refresh_brush_cursor(self) -> None:
        if self._active_tool in _SHAPE_TOOLS:
            if hasattr(self, "canvas"):
                self.canvas.delete("brush-cursor")
            return
        super()._refresh_brush_cursor()

    def _clear_shape_preview(self) -> None:
        self._shape_start = None
        self._shape_last = None
        if hasattr(self, "canvas"):
            self.canvas.delete("shape-preview")

    @staticmethod
    def _shift_pressed(state: int) -> bool:
        return bool(state & _SHIFT_MASK)

    @staticmethod
    def _alt_pressed(state: int) -> bool:
        return any(state & mask for mask in _ALT_MASKS)

    @staticmethod
    def _line_preview_points(
        left: float,
        top: float,
        right: float,
        bottom: float,
        orientation: str,
    ) -> tuple[float, float, float, float]:
        if orientation == "right_down":
            return left, top, right, bottom
        if orientation == "right_up":
            return left, bottom, right, top
        if orientation == "left_down":
            return right, top, left, bottom
        return right, bottom, left, top

    @staticmethod
    def _polygon_preview_points(
        left: float,
        top: float,
        right: float,
        bottom: float,
        sides: int,
    ) -> tuple[float, ...]:
        count = max(3, min(12, sides))
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        radius_x = (right - left) / 2
        radius_y = (bottom - top) / 2
        coordinates: list[float] = []
        for index in range(count):
            angle = -math.pi / 2 + index * math.tau / count
            coordinates.extend(
                (
                    center_x + math.cos(angle) * radius_x,
                    center_y + math.sin(angle) * radius_y,
                )
            )
        return tuple(coordinates)

    @property
    def _shape_session(self) -> ShapeProjectSession:
        if not isinstance(self.session, ShapeProjectSession):
            raise RuntimeError("The editor requires a shape-enabled project session.")
        return self.session
