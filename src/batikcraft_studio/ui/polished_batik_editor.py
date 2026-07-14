"""Polished Batik workspace with icon-only tools and color-aware selection."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import colorchooser, ttk

from batikcraft_studio.application import (
    InteractiveTransformProjectSession,
    ProjectSessionError,
)
from batikcraft_studio.domain import LayerObject, ObjectKind, ProjectValidationError
from batikcraft_studio.i18n import tr

from .object_colors import (
    declared_layer_colors,
    declared_object_colors,
    dominant_raster_colors,
)
from .precise_transform_editor import PreciseTransformEditorWorkspaceView
from .tooltip import ToolTip
from .widgets import icon_button


class PolishedBatikEditorWorkspaceView(PreciseTransformEditorWorkspaceView):
    """Use compact icons and keep the palette synchronized with selected artwork."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._canvas_color_preview: tk.Button | None = None
        self._raster_palette_cache: dict[str, tuple[str | None, str | None]] = {}
        super().__init__(*args, **kwargs)
        self.tools_host.configure(width=104)
        self.tools_panel.floating_size = (150, 500)
        self._refresh_canvas_color_preview()

    def _build_batik_toolbox(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        grid = ttk.Frame(parent, style="Dock.TFrame")
        grid.grid(row=0, column=0, sticky="nsew")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self._batik_tool_buttons = {}
        tools: tuple[tuple[str, str, str, Callable[[], object]], ...] = (
            ("select", "select", "toolbox.select", self.activate_select_tool),
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
                size=24,
            )
            button.grid(row=row, column=column, sticky="nsew", padx=2, pady=2, ipady=6)
            self._batik_tool_buttons[key] = button

        settings = icon_button(
            parent,
            icon="editor",
            tooltip=tr("toolbox.options"),
            command=self.open_active_tool_settings,
            style="Secondary.TButton",
            size=20,
        )
        settings.grid(row=1, column=0, sticky="ew", pady=(8, 0), ipady=4)
        self._update_tool_button_styles()

    def _build_color_palette(self, parent: ttk.Frame) -> None:
        super()._build_color_palette(parent)
        canvas_controls = ttk.Frame(parent, style="Toolbar.TFrame")
        canvas_controls.grid(row=0, column=3, sticky="e", padx=(10, 0))
        ttk.Label(
            canvas_controls,
            text=tr("palette.canvas"),
            style="PanelTitle.TLabel",
        ).pack(side="left", padx=(0, 5))
        self._canvas_color_preview = tk.Button(
            canvas_controls,
            width=4,
            height=1,
            relief=tk.RAISED,
            borderwidth=2,
            cursor="hand2",
            command=self._choose_canvas_color,
        )
        self._canvas_color_preview.pack(side="left")
        ToolTip(self._canvas_color_preview, tr("palette.canvas_tooltip"))
        self._refresh_canvas_color_preview()

    def refresh_project(self) -> None:
        super().refresh_project()
        self._refresh_canvas_color_preview()

    def _on_tree_select(self, event: tk.Event[tk.Misc]) -> None:
        super()._on_tree_select(event)
        self.after_idle(lambda: self._sync_palette_from_selection(announce=True))

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        super()._on_canvas_press(event)
        if self._active_tool == "select":
            self.after_idle(lambda: self._sync_palette_from_selection(announce=True))

    def _choose_canvas_color(self) -> None:
        project = self.session.project
        if project is None:
            self.set_status(tr("library.project_required"))
            return
        _rgb, selected = colorchooser.askcolor(
            color=project.canvas.background_color,
            parent=self.winfo_toplevel(),
            title=tr("palette.choose_canvas"),
        )
        if not selected:
            return
        try:
            color = self._color_session.set_canvas_background(selected)
        except (ProjectSessionError, ProjectValidationError) as exc:
            self.set_status(str(exc))
            return
        self._refresh_canvas_color_preview()
        self.refresh_context()
        self.set_status(tr("palette.canvas_set", color=color))

    def _refresh_canvas_color_preview(self) -> None:
        button = self._canvas_color_preview
        if button is None or not button.winfo_exists():
            return
        project = self.session.project
        color = project.canvas.background_color if project is not None else "#FFFFFF"
        button.configure(background=color, activebackground=color)

    def _sync_palette_from_selection(self, *, announce: bool) -> None:
        project = self.session.project
        if project is None:
            return
        item = self._active_object()
        name: str | None = None
        primary: str | None = None
        secondary: str | None = None
        if item is not None:
            name = item.name
            primary, secondary = declared_object_colors(item)
            if item.kind is not ObjectKind.ERASER_STROKE and item.asset_ref is not None:
                sampled = self._sampled_object_colors(item)
                primary = primary or sampled[0]
                secondary = secondary or sampled[1]
        else:
            layer = self._active_layer()
            if layer is not None:
                name = layer.name
                primary, secondary = declared_layer_colors(layer)
                if layer.asset_ref is not None:
                    sampled = self._sampled_asset_colors(layer.asset_ref)
                    primary = primary or sampled[0]
                    secondary = secondary or sampled[1]

        if primary is None and secondary is None:
            return
        if primary is not None:
            self._set_primary_color(primary, announce=False)
        if secondary is not None and secondary != primary:
            self._set_secondary_color(secondary, announce=False)
        if announce and name is not None:
            self.set_status(tr("palette.object_synced", name=name))

    def _sampled_object_colors(
        self,
        item: LayerObject,
    ) -> tuple[str | None, str | None]:
        return self._sampled_asset_colors(item.asset_ref)

    def _sampled_asset_colors(
        self,
        asset_ref: str | None,
    ) -> tuple[str | None, str | None]:
        if asset_ref is None:
            return (None, None)
        cached = self._raster_palette_cache.get(asset_ref)
        if cached is not None:
            return cached
        content = self.session.assets.get(asset_ref)
        if content is None:
            return (None, None)
        project = self.session.project
        canvas_color = project.canvas.background_color if project is not None else "#FFFFFF"
        colors = dominant_raster_colors(content, canvas_color=canvas_color)
        self._raster_palette_cache[asset_ref] = colors
        return colors

    @property
    def _color_session(self) -> InteractiveTransformProjectSession:
        if not isinstance(self.session, InteractiveTransformProjectSession):
            raise RuntimeError("Editor warna memerlukan InteractiveTransformProjectSession.")
        return self.session


__all__ = ["PolishedBatikEditorWorkspaceView"]
