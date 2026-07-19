"""Contextual Batik tool options, destructive erasing, and tab-capable dock panels."""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from batikcraft_studio.application import DestructiveEraserProjectSession, ProjectSessionError
from batikcraft_studio.i18n import tr

from .context_tool_i18n import install_context_tool_translations
from .direct_style_editor import DirectStyleEditorWorkspaceView
from .tabbed_dockable_panel import TabbedDockablePanel
from .theme import COLORS
from .tool_icons import create_tool_icon
from .tooltip import ToolTip

install_context_tool_translations()

_PAINT_VARIANTS = frozenset({"canting", "brush", "pencil", "eraser"})
_SHAPE_VARIANTS = frozenset({"line", "rectangle", "ellipse", "polygon"})


class ContextToolEditorWorkspaceView(DirectStyleEditorWorkspaceView):
    """Show tool controls only on demand and erase pixels from existing objects."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._tool_options_key: str | None = None
        self._tool_options_expanded = False
        self._tool_options_host: ttk.Frame | None = None
        self._eraser_target_object_id: str | None = None
        super().__init__(*args, **kwargs)

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.tools_host = ttk.Frame(self, style="Dock.TFrame", width=190)
        self.tools_host.grid(row=0, column=0, sticky="nsw")
        self.tools_host.grid_propagate(False)
        self.tools_host.columnconfigure(0, weight=1)
        self.tools_host.rowconfigure(0, weight=1)

        canvas_shell = ttk.Frame(self, style="App.TFrame")
        canvas_shell.grid(row=0, column=1, sticky="nsew")
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

        self.right_shell = ttk.Frame(self, style="Dock.TFrame", width=350)
        self.right_shell.grid(row=0, column=2, sticky="nse")
        self.right_shell.grid_propagate(False)
        self.right_shell.columnconfigure(0, weight=1)
        self.right_shell.rowconfigure(0, weight=1)
        self.right_shell.rowconfigure(1, weight=1)

        self.right_paned = ttk.PanedWindow(self.right_shell, orient=tk.VERTICAL, width=350)
        self.right_paned.grid(row=0, column=0, sticky="nsew")
        self.asset_host = ttk.Frame(self.right_paned, style="Dock.TFrame", width=350)
        self.asset_host.columnconfigure(0, weight=1)
        self.asset_host.rowconfigure(0, weight=1)
        self.layers_host = ttk.Frame(self.right_paned, style="Dock.TFrame", width=350)
        self.layers_host.columnconfigure(0, weight=1)
        self.layers_host.rowconfigure(0, weight=1)

        self.panel_tabs = ttk.Notebook(self.right_shell)
        self.panel_tabs.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        self.panel_tabs.grid_remove()

        self.palette_host = ttk.Frame(self, style="Toolbar.TFrame", padding=(6, 5))
        self.palette_host.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.palette_host.columnconfigure(1, weight=1)
        self._build_color_palette(self.palette_host)

        self.tools_panel = TabbedDockablePanel(
            self,
            key="tools",
            title=tr("dock.tools"),
            host=self.tools_host,
            tab_host=self.panel_tabs,
            builder=self._build_batik_toolbox,
            on_state_change=self._sync_panel_layout,
            floating_size=(270, 620),
        )
        self._dock_panels["tools"] = self.tools_panel
        self.asset_panel = TabbedDockablePanel(
            self,
            key="assets",
            title=tr("library.title"),
            host=self.asset_host,
            tab_host=self.panel_tabs,
            builder=self._build_library_panel,
            on_state_change=self._sync_panel_layout,
            floating_size=(430, 640),
        )
        self._dock_panels["assets"] = self.asset_panel
        self.layers_panel = TabbedDockablePanel(
            self,
            key="layers",
            title=tr("tree.title"),
            host=self.layers_host,
            tab_host=self.panel_tabs,
            builder=self._build_layers_panel,
            on_state_change=self._sync_panel_layout,
            floating_size=(390, 560),
        )
        self._dock_panels["layers"] = self.layers_panel
        self._sync_panel_layout()

    def _sync_panel_layout(self) -> None:
        tools_docked = getattr(self, "tools_panel", None) is not None and self.tools_panel.is_docked
        if tools_docked:
            self.tools_host.grid()
        else:
            self.tools_host.grid_remove()

        if hasattr(self, "right_paned"):
            for host in (self.asset_host, self.layers_host):
                if str(host) in self.right_paned.panes():
                    self.right_paned.forget(host)
            if getattr(self, "asset_panel", None) is not None and self.asset_panel.is_docked:
                self.right_paned.add(self.asset_host, weight=3)
            if getattr(self, "layers_panel", None) is not None and self.layers_panel.is_docked:
                self.right_paned.add(self.layers_host, weight=2)
            if self.right_paned.panes():
                self.right_paned.grid()
            else:
                self.right_paned.grid_remove()

        tabbed = any(
            getattr(panel, "is_tabbed", False) for panel in self._dock_panels.values()
        )
        if tabbed:
            self.panel_tabs.grid()
        else:
            self.panel_tabs.grid_remove()
        if self.right_paned.panes() or tabbed:
            self.right_shell.grid()
        else:
            self.right_shell.grid_remove()

    def _sync_tools_host(self) -> None:
        self._sync_panel_layout()

    def _sync_right_docks(self) -> None:
        self._sync_panel_layout()

    def _build_batik_toolbox(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        # Sidebar ringkas: host lebih sempit, isi 3 kolom ikon, dan dapat
        # digulir bila tinggi jendela terbatas.
        try:
            self.tools_host.configure(width=150)
        except tk.TclError:
            pass
        outer = tk.Canvas(
            parent,
            highlightthickness=0,
            borderwidth=0,
            width=138,
            background=COLORS.get("dock", COLORS.get("surface", "#EEE9E1")),
        )
        outer.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=outer.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        outer.configure(yscrollcommand=scrollbar.set)
        grid = ttk.Frame(outer, style="Dock.TFrame")
        window_id = outer.create_window((0, 0), window=grid, anchor="nw")

        def _sync_scrollregion(_event: object = None) -> None:
            try:
                outer.configure(scrollregion=outer.bbox("all"))
                outer.itemconfigure(window_id, width=outer.winfo_width())
            except tk.TclError:
                pass

        grid.bind("<Configure>", _sync_scrollregion)
        outer.bind("<Configure>", _sync_scrollregion)

        def _wheel(event: tk.Event) -> str:
            outer.yview_scroll(-1 if getattr(event, "delta", 0) > 0 else 1, "units")
            return "break"

        for sequence in ("<MouseWheel>",):
            outer.bind(sequence, _wheel)
            grid.bind(sequence, _wheel)
        outer.bind("<Button-4>", lambda _e: (outer.yview_scroll(-1, "units"), "break")[1])
        outer.bind("<Button-5>", lambda _e: (outer.yview_scroll(1, "units"), "break")[1])

        for column in range(3):
            grid.columnconfigure(column, weight=1)
        self._batik_tool_buttons = {}
        tools: tuple[tuple[str, str, str, Callable[[], object]], ...] = (
            ("select", "select_tool", "toolbox.select", self.activate_select_tool),
            ("hand", "hand_tool", "toolbox.hand", self.activate_hand_tool),
            ("fill", "fill_tool", "toolbox.fill", self.activate_fill_tool),
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
        for index, (key, icon_name, label_key, action) in enumerate(tools):
            row, column = divmod(index, 3)
            button = self._tool_icon_button(
                grid,
                icon_name,
                tr(label_key),
                lambda tool=key, command=action: self._activate_context_tool(tool, command),
                size=19,
            )
            button.grid(row=row, column=column, sticky="nsew", padx=1, pady=1, ipady=2)
            self._batik_tool_buttons[key] = button

        # Opsi tool kini tampil sebagai jendela terpisah, bukan menempel di sidebar.
        self._tool_options_host = None
        self._tool_options_window: tk.Toplevel | None = None
        self._update_tool_button_styles()

    def _tool_icon_button(
        self,
        parent: tk.Misc,
        icon_name: str,
        tooltip: str,
        command: Callable[[], object],
        *,
        size: int = 22,
        style: str = "Tool.TButton",
    ) -> ttk.Button:
        image = create_tool_icon(parent, icon_name, size=size)
        button = ttk.Button(parent, image=image, command=command, style=style, takefocus=True)
        button.image = image  # type: ignore[attr-defined]
        ToolTip(button, tooltip)
        return button

    def _activate_context_tool(self, key: str, action: Callable[[], object]) -> None:
        same_tool = self._batik_tool_variant == key
        if not same_tool:
            action()
            self._show_tool_options(key)
            return
        if self._tool_options_expanded and self._tool_options_key == key:
            self._hide_tool_options()
        else:
            self._show_tool_options(key)

    def _show_tool_options(self, key: str) -> None:
        window = getattr(self, "_tool_options_window", None)
        if window is not None and window.winfo_exists():
            window.destroy()
        window = tk.Toplevel(self)
        window.title(tr("context.options", tool=tr(f"toolbox.{key}")))
        window.transient(self.winfo_toplevel())
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", self._hide_tool_options)
        try:
            root = self.winfo_toplevel()
            x = root.winfo_rootx() + 160
            y = root.winfo_rooty() + 90
            window.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        body = ttk.Frame(window, padding=(10, 8))
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        panel = ttk.LabelFrame(
            body,
            text=tr("context.options", tool=tr(f"toolbox.{key}")),
            padding=(7, 6),
        )
        panel.grid(row=0, column=0, sticky="ew")
        panel.columnconfigure(0, weight=1)
        if key == "fill":
            self._build_fill_options(panel)
        elif key in _PAINT_VARIANTS:
            self._build_paint_options(panel, key)
        elif key in _SHAPE_VARIANTS:
            self._build_shape_options(panel)
        else:
            self._build_dialog_options(panel)
        self._tool_options_window = window
        self._tool_options_key = key
        self._tool_options_expanded = True

    def _hide_tool_options(self) -> None:
        window = getattr(self, "_tool_options_window", None)
        if window is not None and window.winfo_exists():
            window.destroy()
        self._tool_options_window = None
        self._tool_options_expanded = False

    def _build_fill_options(self, parent: ttk.Frame) -> None:
        self._tool_color_preview = tk.Button(
            parent,
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
                parent,
                text=tr(label_key),
                value=value,
                variable=self.style_target_value,
            ).grid(row=1, column=column, sticky="w", padx=(0, 4))
        self._update_color_previews()

    def _build_paint_options(self, parent: ttk.Frame, key: str) -> None:
        self._build_compact_slider(
            parent,
            row=0,
            label=tr("direct.brush_size"),
            variable=self.brush_size_value,
            start=1,
            stop=256,
        )
        self._build_compact_slider(
            parent,
            row=2,
            label=tr("direct.softness"),
            variable=self.brush_softness_value,
            start=0,
            stop=100,
        )
        self._build_compact_slider(
            parent,
            row=4,
            label=tr("direct.smoothing"),
            variable=self.brush_smoothing_value,
            start=0,
            stop=100,
        )
        ttk.Label(
            parent,
            text=tr("context.eraser_destructive") if key == "eraser" else tr("context.click_again"),
            style="Muted.TLabel",
            wraplength=210,
            justify="left",
        ).grid(row=6, column=0, sticky="ew", pady=(4, 0))

    def _build_shape_options(self, parent: ttk.Frame) -> None:
        ttk.Checkbutton(
            parent,
            text=tr("direct.outline"),
            variable=self.stroke_visible_value,
            command=self._apply_stroke_visibility_from_sidebar,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(parent, text=tr("direct.outline_width")).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(5, 0),
        )
        width = ttk.Spinbox(
            parent,
            from_=0.1,
            to=512,
            increment=0.5,
            textvariable=self.shape_stroke_width,
            width=7,
            command=self._apply_shape_stroke_width_from_sidebar,
        )
        width.grid(row=2, column=0, sticky="ew")
        width.bind("<Return>", lambda _event: self._apply_shape_stroke_width_from_sidebar())
        self._build_dialog_options(parent, row=3)

    def _build_dialog_options(self, parent: ttk.Frame, *, row: int = 0) -> None:
        button = self._tool_icon_button(
            parent,
            "options_tool",
            tr("toolbox.options"),
            self.open_active_tool_settings,
            size=19,
            style="Secondary.TButton",
        )
        button.grid(row=row, column=0, sticky="ew", pady=(6, 0), ipady=3)

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "eraser":
            super()._on_canvas_press(event)
            return
        point = self._project_point(event.x, event.y)
        project = self.session.project
        if point is None or project is None:
            return
        hit = self._hit_topmost_object(point)
        if hit is None:
            self.set_status(tr("context.eraser_object_required"))
            return
        self._eraser_session.select_object_for_editing(hit.object_id)
        self._eraser_target_object_id = hit.object_id
        self._stroke_points = [point]
        self._stroke_last_screen = (event.x, event.y)
        self.canvas.delete("paint-preview")
        self._draw_preview_dot(event.x, event.y)

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "eraser":
            super()._on_canvas_drag(event)
            return
        if self._eraser_target_object_id is None or self._stroke_last_screen is None:
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
        if self._active_tool != "eraser":
            super()._on_canvas_release(event)
            return
        object_id = self._eraser_target_object_id
        if object_id is None:
            self._clear_context_eraser()
            return
        point = self._project_point(event.x, event.y)
        if point is not None and (not self._stroke_points or point != self._stroke_points[-1]):
            self._stroke_points.append(point)
        try:
            updated = self._eraser_session.erase_object_pixels(
                object_id,
                points=tuple(self._stroke_points),
                brush_size=float(self.brush_size_value.get()),
                opacity=self._percentage(self.brush_opacity_value),
                hardness=self._percentage(self.brush_hardness_value),
                smoothing=self._percentage(self.brush_smoothing_value),
            )
        except (ProjectSessionError, ValueError) as exc:
            self.set_status(str(exc))
            self._clear_context_eraser()
            self._schedule_render()
            return
        self._clear_context_eraser()
        self.refresh_context()
        self.set_status(tr("context.eraser_applied", name=updated.name))

    def _clear_context_eraser(self) -> None:
        self._eraser_target_object_id = None
        self._clear_paint_stroke()

    @property
    def _eraser_session(self) -> DestructiveEraserProjectSession:
        if not isinstance(self.session, DestructiveEraserProjectSession):
            raise RuntimeError("Editor penghapus memerlukan DestructiveEraserProjectSession.")
        return self.session


__all__ = ["ContextToolEditorWorkspaceView"]
