"""Direct styling sidebar, mouse-wheel zoom, and layer-tree drag/drop."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from batikcraft_studio.application import DirectStyleProjectSession, ProjectSessionError
from batikcraft_studio.domain import ObjectKind
from batikcraft_studio.i18n import tr

from .direct_style_i18n import install_direct_style_translations
from .viewport_editor import ViewportEditorWorkspaceView
from .widgets import icon_button

install_direct_style_translations()

_SHIFT_MASK = 0x0001


class DirectStyleEditorWorkspaceView(ViewportEditorWorkspaceView):
    """Expose color, fill, stroke, brush feel, and tree movement directly."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        parent = args[0] if args else kwargs["parent"]
        self.style_target_value = tk.StringVar(master=parent, value="auto")
        self.stroke_visible_value = tk.BooleanVar(master=parent, value=True)
        self.brush_softness_value = tk.DoubleVar(master=parent, value=55.0)
        self._tool_color_preview: tk.Button | None = None
        self._syncing_softness = False
        self._tree_drag_source: str | None = None
        self._tree_drag_start: tuple[int, int] | None = None
        self._tree_dragging = False
        super().__init__(*args, **kwargs)
        self.tools_host.configure(width=224)
        self.tools_panel.floating_size = (300, 720)
        self.brush_softness_value.set(100.0 - float(self.brush_hardness_value.get()))
        self.brush_softness_value.trace_add("write", self._sync_hardness_from_softness)
        self.brush_hardness_value.trace_add("write", self._sync_softness_from_hardness)
        self.layer_tree.bind("<ButtonPress-1>", self._on_tree_drag_press, add="+")
        self.layer_tree.bind("<B1-Motion>", self._on_tree_drag_motion, add="+")
        self.layer_tree.bind("<ButtonRelease-1>", self._on_tree_drag_release, add="+")

    def _build_batik_toolbox(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        grid = ttk.Frame(parent, style="Dock.TFrame")
        grid.grid(row=0, column=0, sticky="nsew")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self._batik_tool_buttons = {}
        tools = (
            ("select", "select", "toolbox.select", self.activate_select_tool),
            ("fill", "apply", "toolbox.fill", self.activate_fill_tool),
            ("canting", "canting_tool", "toolbox.canting", self.activate_canting_tool),
            ("brush", "brush_tool", "toolbox.brush", self.activate_soft_brush_tool),
            ("pencil", "pencil_tool", "toolbox.pencil", self.activate_pencil_tool),
            ("eraser", "eraser_tool", "toolbox.eraser", self.activate_eraser_tool),
            ("line", "line_tool", "toolbox.line", lambda: self.activate_shape_tool("line")),
            (
                "rectangle",
                "rectangle_tool",
                "toolbox.rectangle",
                lambda: self.activate_shape_tool("rectangle"),
            ),
            (
                "ellipse",
                "ellipse_tool",
                "toolbox.ellipse",
                lambda: self.activate_shape_tool("ellipse"),
            ),
            (
                "polygon",
                "polygon_tool",
                "toolbox.polygon",
                lambda: self.activate_shape_tool("polygon"),
            ),
            ("motif", "motif_tool", "toolbox.motif", self.activate_cap_motif_tool),
            ("isen", "isen_tool", "toolbox.isen", self.activate_cap_isen_tool),
        )
        for index, (key, icon, label_key, command) in enumerate(tools):
            row, column = divmod(index, 2)
            button = icon_button(
                grid,
                icon=icon,
                tooltip=tr(label_key),
                command=command,
                style=(
                    "ToolActive.TButton"
                    if key == self._batik_tool_variant
                    else "Tool.TButton"
                ),
                size=22,
            )
            button.grid(row=row, column=column, sticky="nsew", padx=2, pady=2, ipady=5)
            self._batik_tool_buttons[key] = button

        controls = ttk.LabelFrame(parent, text=tr("direct.color"), padding=(7, 6))
        controls.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        controls.columnconfigure(0, weight=1)
        self._tool_color_preview = tk.Button(
            controls,
            height=2,
            relief=tk.RAISED,
            borderwidth=2,
            cursor="hand2",
            command=lambda: self._choose_palette_color(primary=True),
        )
        self._tool_color_preview.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        for column, (label_key, value) in enumerate(
            (
                ("direct.target.auto", "auto"),
                ("direct.target.fill", "fill"),
                ("direct.target.stroke", "stroke"),
            )
        ):
            ttk.Radiobutton(
                controls,
                text=tr(label_key),
                value=value,
                variable=self.style_target_value,
            ).grid(row=1, column=column, sticky="w", padx=(0, 4))

        brush = ttk.LabelFrame(parent, text=tr("direct.brush_size"), padding=(7, 6))
        brush.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        brush.columnconfigure(0, weight=1)
        self._build_compact_slider(
            brush,
            row=0,
            label=tr("direct.brush_size"),
            variable=self.brush_size_value,
            start=1,
            stop=256,
        )
        self._build_compact_slider(
            brush,
            row=2,
            label=tr("direct.softness"),
            variable=self.brush_softness_value,
            start=0,
            stop=100,
        )
        self._build_compact_slider(
            brush,
            row=4,
            label=tr("direct.smoothing"),
            variable=self.brush_smoothing_value,
            start=0,
            stop=100,
        )

        outline = ttk.LabelFrame(parent, text=tr("direct.target.stroke"), padding=(7, 6))
        outline.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        outline.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            outline,
            text=tr("direct.outline"),
            variable=self.stroke_visible_value,
            command=self._apply_stroke_visibility_from_sidebar,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(outline, text=tr("direct.outline_width")).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(5, 0),
        )
        stroke_width = ttk.Spinbox(
            outline,
            from_=0.1,
            to=512,
            increment=0.5,
            textvariable=self.shape_stroke_width,
            width=7,
            command=self._apply_shape_stroke_width_from_sidebar,
        )
        stroke_width.grid(row=1, column=1, sticky="e", pady=(5, 0))
        stroke_width.bind(
            "<Return>",
            lambda _event: self._apply_shape_stroke_width_from_sidebar(),
        )
        stroke_width.bind(
            "<FocusOut>",
            lambda _event: self._apply_shape_stroke_width_from_sidebar(),
        )

        options = icon_button(
            parent,
            icon="editor",
            tooltip=tr("toolbox.options"),
            command=self.open_active_tool_settings,
            style="Secondary.TButton",
            size=19,
        )
        options.grid(row=4, column=0, sticky="ew", pady=(8, 0), ipady=3)
        self._update_tool_button_styles()
        self._update_color_previews()

    def _build_compact_slider(
        self,
        parent: ttk.Frame,
        *,
        row: int,
        label: str,
        variable: tk.Variable,
        start: float,
        stop: float,
    ) -> None:
        ttk.Label(parent, text=label, style="Muted.TLabel").grid(
            row=row,
            column=0,
            sticky="w",
        )
        line = ttk.Frame(parent, style="Dock.TFrame")
        line.grid(row=row + 1, column=0, sticky="ew", pady=(2, 5))
        line.columnconfigure(0, weight=1)
        ttk.Scale(
            line,
            from_=start,
            to=stop,
            variable=variable,
            orient=tk.HORIZONTAL,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Spinbox(
            line,
            from_=start,
            to=stop,
            increment=1,
            textvariable=variable,
            width=5,
        ).grid(row=0, column=1, padx=(5, 0))

    def activate_fill_tool(self) -> None:
        self._batik_tool_variant = "fill"
        self._active_tool = "fill"
        self.style_target_value.set("fill")
        self._clear_paint_stroke()
        self.canvas.configure(cursor="crosshair")
        self._update_tool_button_styles()
        self.set_status(tr("direct.fill.active"))

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "fill":
            super()._on_canvas_press(event)
            return
        point = self._project_point(event.x, event.y)
        if point is None or self.session.project is None:
            return
        item = self._hit_topmost_object(point)
        if item is None:
            self.set_status(tr("structure.fill.closed_required"))
            return
        self._direct_session.select_object_for_editing(item.object_id)
        try:
            self._direct_session.fill_closed_object(
                item.object_id,
                self.foreground_color_value.get(),
            )
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            self._refresh_multi_selection()
            return
        self.refresh_context()
        self.set_status(
            tr("direct.fill.applied", color=self.foreground_color_value.get().upper())
        )

    def _set_primary_color(self, color: str, *, announce: bool = True) -> None:
        super()._set_primary_color(color, announce=False)
        if announce:
            self._apply_palette_color_to_selection(color)

    def _set_secondary_color(self, color: str, *, announce: bool = True) -> str:
        result = super()._set_secondary_color(color, announce=False)
        if announce:
            self._apply_palette_color_to_selection(color, fallback_target="fill")
        return result

    def _apply_palette_color_to_selection(
        self,
        color: str,
        *,
        fallback_target: str | None = None,
    ) -> None:
        selected = self._direct_session.selected_object_ids
        if not selected:
            self.set_status(tr("palette.primary_set", color=color.upper()))
            return
        target = fallback_target or self.style_target_value.get()
        try:
            updated = self._direct_session.apply_color_to_selected(color, target=target)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(
            tr("direct.color.applied", color=color.upper(), count=len(updated))
        )

    def _refresh_transform_fields(self) -> None:
        super()._refresh_transform_fields()
        item = self._active_object()
        if item is None or item.kind is not ObjectKind.SHAPE:
            return
        self.stroke_visible_value.set(bool(item.properties.get("stroke_enabled", True)))

    def _apply_stroke_visibility_from_sidebar(self) -> None:
        try:
            updated = self._direct_session.set_selected_shape_stroke_enabled(
                bool(self.stroke_visible_value.get())
            )
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(tr("direct.stroke.updated", count=len(updated)))

    def _apply_shape_stroke_width_from_sidebar(self) -> None:
        if not self._direct_session.selected_object_ids:
            return
        try:
            updated = self._direct_session.set_selected_shape_stroke_width(
                float(self.shape_stroke_width.get())
            )
        except (ProjectSessionError, ValueError, tk.TclError) as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(tr("direct.stroke.updated", count=len(updated)))

    def _update_color_previews(self) -> None:
        super()._update_color_previews()
        button = self._tool_color_preview
        if button is not None and button.winfo_exists():
            color = self.foreground_color_value.get()
            button.configure(background=color, activebackground=color)

    def _sync_hardness_from_softness(self, *_args: object) -> None:
        if self._syncing_softness:
            return
        self._syncing_softness = True
        try:
            softness = min(100.0, max(0.0, float(self.brush_softness_value.get())))
            self.brush_hardness_value.set(100.0 - softness)
        except (ValueError, tk.TclError):
            pass
        finally:
            self._syncing_softness = False

    def _sync_softness_from_hardness(self, *_args: object) -> None:
        if self._syncing_softness:
            return
        self._syncing_softness = True
        try:
            hardness = min(100.0, max(0.0, float(self.brush_hardness_value.get())))
            self.brush_softness_value.set(100.0 - hardness)
        except (ValueError, tk.TclError):
            pass
        finally:
            self._syncing_softness = False

    def open_active_tool_settings(self) -> None:
        if self._batik_tool_variant == "fill":
            self.style_target_value.set("fill")
            self.set_status(tr("direct.fill.active"))
            return
        super().open_active_tool_settings()

    def _on_mousewheel(self, event: tk.Event[tk.Canvas]) -> str:
        if event.state & _SHIFT_MASK:
            return self._on_shift_mousewheel(event)
        if event.delta > 0:
            self.zoom_in()
        elif event.delta < 0:
            self.zoom_out()
        return "break"

    def _on_linux_wheel_up(self, event: tk.Event[tk.Canvas]) -> str:
        if event.state & _SHIFT_MASK:
            self.canvas.xview_scroll(-1, "units")
            self._draw_rulers()
        else:
            self.zoom_in()
        return "break"

    def _on_linux_wheel_down(self, event: tk.Event[tk.Canvas]) -> str:
        if event.state & _SHIFT_MASK:
            self.canvas.xview_scroll(1, "units")
            self._draw_rulers()
        else:
            self.zoom_out()
        return "break"

    def _on_tree_drag_press(self, event: tk.Event[ttk.Treeview]) -> None:
        iid = self.layer_tree.identify_row(event.y)
        self._tree_drag_source = iid or None
        self._tree_drag_start = (event.x, event.y) if iid else None
        self._tree_dragging = False

    def _on_tree_drag_motion(self, event: tk.Event[ttk.Treeview]) -> None:
        if self._tree_drag_source is None or self._tree_drag_start is None:
            return
        if abs(event.x - self._tree_drag_start[0]) + abs(event.y - self._tree_drag_start[1]) < 6:
            return
        self._tree_dragging = True
        self.layer_tree.configure(cursor="fleur")
        target = self.layer_tree.identify_row(event.y)
        if target:
            self.layer_tree.focus(target)

    def _on_tree_drag_release(self, event: tk.Event[ttk.Treeview]) -> None:
        source = self._tree_drag_source
        target = self.layer_tree.identify_row(event.y)
        dragging = self._tree_dragging
        self._tree_drag_source = None
        self._tree_drag_start = None
        self._tree_dragging = False
        self.layer_tree.configure(cursor="")
        if not dragging or not source or not target or source == target:
            return
        try:
            moved_iid = self._direct_session.move_tree_node(source, target)
        except ProjectSessionError as exc:
            self.set_status(tr("direct.layer.drag_error", message=str(exc)))
            return
        self.refresh_context()
        self.after_idle(lambda: self._select_moved_tree_item(moved_iid))
        self.set_status(tr("direct.layer.moved"))

    def _select_moved_tree_item(self, iid: str) -> None:
        if self.layer_tree.exists(iid):
            self.layer_tree.selection_set(iid)
            self.layer_tree.focus(iid)
            self.layer_tree.see(iid)

    @property
    def _direct_session(self) -> DirectStyleProjectSession:
        if not isinstance(self.session, DirectStyleProjectSession):
            raise RuntimeError("Editor gaya langsung memerlukan DirectStyleProjectSession.")
        return self.session


__all__ = ["DirectStyleEditorWorkspaceView"]
