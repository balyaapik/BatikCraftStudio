"""Asset-first editor with dockable Batik tools, library, layers, and color palette."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageTk, UnidentifiedImageError

from batikcraft_studio.application import ProjectSessionError
from batikcraft_studio.assets import (
    ASSET_PACK_EXTENSION,
    AssetLibrary,
    AssetLibraryError,
    AssetRecord,
)
from batikcraft_studio.i18n import category_label, tr
from batikcraft_studio.imaging import ASSET_CATEGORIES, BatikAssetError, load_batik_asset

from .dockable_panel import DockablePanel
from .icons import create_icon
from .keyboard import run_single_key_shortcut
from .professional_object_tree_editor import ProfessionalObjectTreeEditorWorkspaceView
from .theme import COLORS
from .tool_windows import EditorToolWindows
from .widgets import icon_button

_MAX_VISIBLE_RESULTS = 5_000
_BRUSH_VARIANTS = {"canting", "brush", "pencil"}
_SHAPE_VARIANTS = {"line", "rectangle", "ellipse", "polygon"}
_BATIK_PALETTE = (
    "#1C1714",
    "#3A2318",
    "#4E2A1E",
    "#6A3924",
    "#7A3E2A",
    "#8B5A2B",
    "#A46732",
    "#C8873A",
    "#D9A566",
    "#E6C18A",
    "#F4E9D8",
    "#FFF8E9",
    "#1F2A44",
    "#273B5B",
    "#31506F",
    "#426B86",
    "#648BA1",
    "#93AEB8",
    "#173F35",
    "#285849",
    "#3F755E",
    "#6F9275",
    "#9CAF88",
    "#C2C9A8",
    "#6D1826",
    "#8F2435",
    "#B13A45",
    "#D2665A",
    "#DE8B6F",
    "#E7B49E",
    "#55345F",
    "#79517E",
    "#9C77A0",
    "#505050",
    "#8A8178",
    "#D2CBC1",
)


class CompactAssetEditorWorkspaceView(ProfessionalObjectTreeEditorWorkspaceView):
    """Professional Batik workspace with independently dockable side panels."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        parent = args[0] if args else kwargs["parent"]
        self.asset_library = AssetLibrary()
        self._all_packs_label = tr("library.all_packs")
        self._all_categories_label = tr("library.all_categories")
        self._category_display_to_id = {
            category_label(category): category for category in ASSET_CATEGORIES
        }
        self.library_query_value = tk.StringVar(master=parent)
        self.library_category_value = tk.StringVar(
            master=parent,
            value=self._all_categories_label,
        )
        self.library_pack_value = tk.StringVar(master=parent, value=self._all_packs_label)
        self.library_summary_value = tk.StringVar(master=parent)
        self.library_asset_name_value = tk.StringVar(
            master=parent,
            value=tr("library.choose_asset"),
        )
        self.library_asset_meta_value = tk.StringVar(master=parent, value="")
        self.foreground_color_value = tk.StringVar(master=parent, value="#4E2A1E")
        self.background_color_value = tk.StringVar(master=parent, value="#F4E9D8")
        self._library_records: dict[str, AssetRecord] = {}
        self._library_pack_lookup: dict[str, str] = {}
        self._library_preview_photo: ImageTk.PhotoImage | None = None
        self._dock_panels: dict[str, DockablePanel] = {}
        self._batik_tool_buttons: dict[str, ttk.Button] = {}
        self._batik_tool_variant = "select"
        self._primary_color_preview: tk.Button | None = None
        self._secondary_color_preview: tk.Button | None = None
        self._syncing_color = False
        super().__init__(*args, **kwargs)
        self.tool_windows = EditorToolWindows(self)
        self.library_query_value.trace_add("write", lambda *_args: self.refresh_library())
        self.library_category_value.trace_add("write", lambda *_args: self.refresh_library())
        self.library_pack_value.trace_add("write", lambda *_args: self.refresh_library())
        self.brush_color_value.trace_add("write", self._sync_primary_from_brush)
        self.motif_isen_color_value.trace_add("write", self._sync_secondary_from_isen)
        self._bind_compact_shortcuts()
        self._set_primary_color(self.foreground_color_value.get(), announce=False)
        self._set_secondary_color(self.background_color_value.get(), announce=False)
        self.refresh_library()
        self._refresh_layer_list()

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

        self.right_paned = ttk.PanedWindow(self, orient=tk.VERTICAL, width=340)
        self.right_paned.grid(row=0, column=2, sticky="nse")
        self.asset_host = ttk.Frame(self.right_paned, style="Dock.TFrame", width=340)
        self.asset_host.columnconfigure(0, weight=1)
        self.asset_host.rowconfigure(0, weight=1)
        self.layers_host = ttk.Frame(self.right_paned, style="Dock.TFrame", width=340)
        self.layers_host.columnconfigure(0, weight=1)
        self.layers_host.rowconfigure(0, weight=1)

        self.palette_host = ttk.Frame(self, style="Toolbar.TFrame", padding=(6, 5))
        self.palette_host.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.palette_host.columnconfigure(1, weight=1)
        self._build_color_palette(self.palette_host)

        self.tools_panel = DockablePanel(
            self,
            key="tools",
            title=tr("dock.tools"),
            host=self.tools_host,
            builder=self._build_batik_toolbox,
            on_state_change=self._sync_tools_host,
            floating_size=(240, 620),
        )
        self._dock_panels["tools"] = self.tools_panel
        self.asset_panel = DockablePanel(
            self,
            key="assets",
            title=tr("library.title"),
            host=self.asset_host,
            builder=self._build_library_panel,
            on_state_change=self._sync_right_docks,
            floating_size=(430, 640),
        )
        self._dock_panels["assets"] = self.asset_panel
        self.layers_panel = DockablePanel(
            self,
            key="layers",
            title=tr("tree.title"),
            host=self.layers_host,
            builder=self._build_layers_panel,
            on_state_change=self._sync_right_docks,
            floating_size=(390, 560),
        )
        self._dock_panels["layers"] = self.layers_panel
        self._sync_right_docks()

    def _build_batik_toolbox(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        grid = ttk.Frame(parent, style="Dock.TFrame")
        grid.grid(row=0, column=0, sticky="nsew")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self._batik_tool_buttons = {}
        tools: tuple[tuple[str, str, str, Callable[[], object]], ...] = (
            ("select", "⌖", "toolbox.select", self.activate_select_tool),
            ("canting", "✒", "toolbox.canting", self.activate_canting_tool),
            ("brush", "●", "toolbox.brush", self.activate_soft_brush_tool),
            ("pencil", "✎", "toolbox.pencil", self.activate_pencil_tool),
            ("eraser", "⌫", "toolbox.eraser", self.activate_eraser_tool),
            ("line", "╱", "toolbox.line", lambda: self.activate_shape_tool("line")),
            (
                "rectangle",
                "▭",
                "toolbox.rectangle",
                lambda: self.activate_shape_tool("rectangle"),
            ),
            ("ellipse", "○", "toolbox.ellipse", lambda: self.activate_shape_tool("ellipse")),
            (
                "polygon",
                "⬡",
                "toolbox.polygon",
                lambda: self.activate_shape_tool("polygon"),
            ),
            ("motif", "✤", "toolbox.motif", self.activate_cap_motif_tool),
            ("isen", "⠿", "toolbox.isen", self.activate_cap_isen_tool),
        )
        for index, (key, symbol, label_key, command) in enumerate(tools):
            row, column = divmod(index, 2)
            button = ttk.Button(
                grid,
                text=f"{symbol}\n{tr(label_key)}",
                style="ToolActive.TButton" if key == self._batik_tool_variant else "Tool.TButton",
                command=command,
                width=9,
            )
            button.grid(row=row, column=column, sticky="nsew", padx=2, pady=2, ipady=5)
            self._batik_tool_buttons[key] = button
        options = ttk.Button(
            parent,
            text=tr("toolbox.options"),
            style="Secondary.TButton",
            command=self.open_active_tool_settings,
        )
        options.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._update_tool_button_styles()

    def _build_layers_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.layer_tree = ttk.Treeview(
            parent,
            show="tree",
            selectmode="browse",
            height=14,
        )
        self.layer_tree.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        self.layer_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.layer_tree.bind("<Button-3>", self._show_tree_context_menu)
        self._tree_icons = {
            "group": create_icon(self, "open", size=15, color="#C8873A"),
            "layer": create_icon(self, "editor", size=15, color="#4677A8"),
            "object": create_icon(self, "batikification", size=14, color="#7D5A9B"),
        }
        controls = ttk.Frame(parent, style="Toolbar.TFrame", padding=(3, 3))
        controls.grid(row=1, column=0, sticky="ew")
        for icon, tooltip_key, command in (
            ("new", "tree.new_tooltip", self._show_new_menu_from_button),
            ("visibility", "tree.visibility", self.toggle_visibility),
            ("lock", "tree.lock", self.toggle_lock),
            ("up", "tree.move_up", self.move_active_up),
            ("down", "tree.move_down", self.move_active_down),
            ("duplicate", "tree.duplicate", self.duplicate_active),
            ("delete", "tree.delete", self.delete_active),
        ):
            icon_button(
                controls,
                icon=icon,
                tooltip=tr(tooltip_key),
                command=command,
                size=18,
            ).pack(side="left", padx=1)
        self._build_tree_menus()
        self.after_idle(self._refresh_layer_list)

    def _build_library_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)
        ttk.Label(
            parent,
            textvariable=self.library_summary_value,
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))

        filters = ttk.Frame(parent, style="Dock.TFrame")
        filters.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        filters.columnconfigure(0, weight=1)
        ttk.Entry(filters, textvariable=self.library_query_value).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 5),
        )
        self.library_pack_combo = ttk.Combobox(
            filters,
            textvariable=self.library_pack_value,
            state="readonly",
        )
        self.library_pack_combo.grid(row=1, column=0, sticky="ew", padx=(0, 4))
        self.library_category_combo = ttk.Combobox(
            filters,
            textvariable=self.library_category_value,
            values=(self._all_categories_label, *self._category_display_to_id),
            state="readonly",
            width=15,
        )
        self.library_category_combo.grid(row=1, column=1, sticky="ew")

        preview = ttk.Frame(parent, style="Surface.TFrame", padding=(7, 7))
        preview.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        preview.columnconfigure(1, weight=1)
        self.library_preview_label = ttk.Label(preview, style="Muted.TLabel", anchor="center")
        self.library_preview_label.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
        ttk.Label(
            preview,
            textvariable=self.library_asset_name_value,
            style="ProjectTitle.TLabel",
            wraplength=190,
            justify="left",
        ).grid(row=0, column=1, sticky="sw")
        ttk.Label(
            preview,
            textvariable=self.library_asset_meta_value,
            style="Muted.TLabel",
            wraplength=190,
            justify="left",
        ).grid(row=1, column=1, sticky="nw", pady=(2, 0))

        self.library_list = ttk.Treeview(
            parent,
            columns=("category", "pack"),
            show="tree headings",
            selectmode="browse",
            height=16,
        )
        self.library_list.heading("#0", text=tr("library.asset_heading"))
        self.library_list.heading("category", text=tr("library.category_heading"))
        self.library_list.heading("pack", text=tr("library.pack_heading"))
        self.library_list.column("#0", width=155, minwidth=90, stretch=True)
        self.library_list.column("category", width=86, minwidth=65, stretch=False)
        self.library_list.column("pack", width=80, minwidth=55, stretch=False)
        self.library_list.grid(row=3, column=0, sticky="nsew")
        self.library_list.bind("<<TreeviewSelect>>", self._on_library_select)
        self.library_list.bind("<Double-1>", lambda _event: self.add_selected_library_asset())

        actions = ttk.Frame(parent, style="Toolbar.TFrame", padding=(3, 3))
        actions.grid(row=4, column=0, sticky="ew", pady=(5, 0))
        for icon, tooltip_key, command in (
            ("apply", "library.add_tooltip", self.add_selected_library_asset),
            ("import", "library.install_tooltip", self.install_asset_pack_dialog),
            ("delete", "library.remove_tooltip", self.uninstall_selected_pack),
            ("redo", "library.reload_tooltip", self.reload_asset_library),
        ):
            icon_button(
                actions,
                icon=icon,
                tooltip=tr(tooltip_key),
                command=command,
                size=18,
            ).pack(side="left", padx=1)
        self.after_idle(self.refresh_library)

    def _build_color_palette(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent, style="Toolbar.TFrame")
        controls.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        ttk.Label(controls, text=tr("palette.title"), style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(0, 3),
        )
        self._primary_color_preview = tk.Button(
            controls,
            width=3,
            height=1,
            relief=tk.SUNKEN,
            borderwidth=2,
            cursor="hand2",
            command=lambda: self._choose_palette_color(primary=True),
        )
        self._primary_color_preview.grid(row=1, column=0, rowspan=2, padx=(0, 3))
        self._secondary_color_preview = tk.Button(
            controls,
            width=3,
            height=1,
            relief=tk.RAISED,
            borderwidth=2,
            cursor="hand2",
            command=lambda: self._choose_palette_color(primary=False),
        )
        self._secondary_color_preview.grid(row=2, column=1, padx=(0, 3))
        ttk.Button(
            controls,
            text="⇄",
            width=3,
            style="Secondary.TButton",
            command=self.swap_palette_colors,
        ).grid(row=1, column=2, padx=1)
        ttk.Button(
            controls,
            text="D",
            width=3,
            style="Secondary.TButton",
            command=self.reset_palette_colors,
        ).grid(row=2, column=2, padx=1)

        swatches = ttk.Frame(parent, style="Toolbar.TFrame")
        swatches.grid(row=0, column=1, sticky="ew")
        for index, color in enumerate(_BATIK_PALETTE):
            row, column = divmod(index, 18)
            button = tk.Button(
                swatches,
                background=color,
                activebackground=color,
                width=2,
                height=1,
                relief=tk.FLAT,
                borderwidth=1,
                highlightthickness=1,
                highlightbackground=COLORS["line"],
                cursor="hand2",
                command=lambda value=color: self._set_primary_color(value),
            )
            button.grid(row=row, column=column, padx=1, pady=1)
            button.bind(
                "<Button-3>",
                lambda _event, value=color: self._set_secondary_color(value),
            )
        ttk.Button(
            parent,
            text=tr("palette.custom"),
            style="Secondary.TButton",
            command=lambda: self._choose_palette_color(primary=True),
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))
        self._update_color_previews()

    def _build_tree_menus(self) -> None:
        self._new_tree_menu = tk.Menu(self, tearoff=False)
        self._new_tree_menu.add_command(label=tr("tree.folder"), command=self._new_folder)
        self._new_tree_menu.add_command(
            label=tr("tree.object_sublayer"),
            command=self._new_object_layer,
        )
        self._new_tree_menu.add_command(
            label=tr("tree.canting_layer"),
            command=self._new_paint_layer_in_tree,
        )
        self._new_tree_menu.add_separator()
        self._new_tree_menu.add_command(
            label=tr("tree.add_from_library"),
            command=self.add_selected_library_asset,
        )
        self._new_tree_menu.add_command(
            label=tr("tree.import_asset"),
            command=self.import_asset_dialog,
        )
        self._tree_context_menu = tk.Menu(self, tearoff=False)
        self._tree_context_menu.add_cascade(label=tr("tree.new"), menu=self._new_tree_menu)
        self._move_folder_menu = tk.Menu(self._tree_context_menu, tearoff=False)
        self._tree_context_menu.add_cascade(
            label=tr("tree.move_to_folder"),
            menu=self._move_folder_menu,
        )
        self._tree_context_menu.add_separator()
        self._tree_context_menu.add_command(
            label=tr("tree.duplicate"),
            command=self.duplicate_active,
        )
        self._tree_context_menu.add_command(
            label=tr("tree.delete"),
            command=self.delete_active,
        )
        self._tree_context_menu.add_separator()
        self._tree_context_menu.add_command(
            label=tr("tree.visibility"),
            command=self.toggle_visibility,
        )
        self._tree_context_menu.add_command(label=tr("tree.lock"), command=self.toggle_lock)

    def _sync_tools_host(self) -> None:
        if self.tools_panel.is_docked:
            self.tools_host.grid()
        else:
            self.tools_host.grid_remove()

    def _sync_right_docks(self) -> None:
        if not hasattr(self, "right_paned"):
            return
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

    def toggle_tools_panel(self) -> None:
        self.tools_panel.toggle()

    def toggle_asset_panel(self) -> None:
        self.asset_panel.toggle()

    def toggle_layers_panel(self) -> None:
        self.layers_panel.toggle()

    def dock_all_panels(self) -> None:
        for panel in self._dock_panels.values():
            panel.dock()

    def activate_hand_tool(self) -> None:
        self._set_active_tool("hand", tr("toolbox.hand_status"))
        if hasattr(self, "canvas"):
            self.canvas.configure(cursor="fleur")

    def activate_select_tool(self) -> None:
        self._batik_tool_variant = "select"
        super().activate_select_tool()

    def activate_canting_tool(self) -> None:
        self.brush_size_value.set(8.0)
        self.brush_opacity_value.set(96.0)
        self.brush_hardness_value.set(88.0)
        self.brush_smoothing_value.set(36.0)
        self._batik_tool_variant = "canting"
        super().activate_brush_tool()
        self.set_status(tr("toolbox.canting_active"))

    def activate_soft_brush_tool(self) -> None:
        self.brush_size_value.set(24.0)
        self.brush_opacity_value.set(72.0)
        self.brush_hardness_value.set(45.0)
        self.brush_smoothing_value.set(58.0)
        self._batik_tool_variant = "brush"
        super().activate_brush_tool()
        self.set_status(tr("toolbox.brush_active"))

    def activate_pencil_tool(self) -> None:
        self.brush_size_value.set(3.0)
        self.brush_opacity_value.set(100.0)
        self.brush_hardness_value.set(100.0)
        self.brush_smoothing_value.set(8.0)
        self._batik_tool_variant = "pencil"
        super().activate_brush_tool()
        self.set_status(tr("toolbox.pencil_active"))

    def activate_eraser_tool(self) -> None:
        self._batik_tool_variant = "eraser"
        super().activate_eraser_tool()

    def activate_shape_tool(self, shape_type: str) -> None:
        self._batik_tool_variant = shape_type
        self._activate_shape_tool(shape_type)

    def activate_cap_motif_tool(self) -> None:
        self._batik_tool_variant = "motif"
        super().activate_cap_motif_tool()

    def activate_cap_isen_tool(self) -> None:
        self._batik_tool_variant = "isen"
        super().activate_cap_isen_tool()

    def _set_active_tool(self, tool: str, status: str) -> None:
        if tool == "hand":
            self._batik_tool_variant = "hand"
        elif tool == "select":
            self._batik_tool_variant = "select"
        elif tool == "eraser":
            self._batik_tool_variant = "eraser"
        elif tool == "brush" and self._batik_tool_variant not in _BRUSH_VARIANTS:
            self._batik_tool_variant = "brush"
        elif tool in _SHAPE_VARIANTS:
            self._batik_tool_variant = tool
        elif tool == "cap_motif":
            self._batik_tool_variant = "motif"
        elif tool == "cap_isen":
            self._batik_tool_variant = "isen"
        super()._set_active_tool(tool, status)
        self._update_tool_button_styles()

    def _update_tool_button_styles(self) -> None:
        for key, button in self._batik_tool_buttons.items():
            if button.winfo_exists():
                button.configure(
                    style="ToolActive.TButton" if key == self._batik_tool_variant else "Tool.TButton"
                )

    def open_active_tool_settings(self) -> None:
        variant = self._batik_tool_variant
        if variant in _BRUSH_VARIANTS:
            self.open_brush_settings()
        elif variant == "eraser":
            self.open_eraser_settings()
        elif variant in _SHAPE_VARIANTS:
            self.open_shape_settings(variant)
        elif variant == "motif":
            self.open_motif_settings()
        elif variant == "isen":
            self.open_isen_settings()
        else:
            self.open_transform_settings()

    def _set_primary_color(self, color: str, *, announce: bool = True) -> None:
        value = color.upper()
        self._syncing_color = True
        try:
            self.foreground_color_value.set(value)
            self.brush_color_value.set(value)
            self.shape_stroke_color.set(value)
            self.cap_color_value.set(value)
            self.motif_color_value.set(value)
        finally:
            self._syncing_color = False
        self._update_color_previews()
        if announce:
            self.set_status(tr("palette.primary_set", color=value))

    def _set_secondary_color(self, color: str, *, announce: bool = True) -> str:
        value = color.upper()
        self._syncing_color = True
        try:
            self.background_color_value.set(value)
            self.shape_fill_color.set(value)
            self.motif_isen_color_value.set(value)
        finally:
            self._syncing_color = False
        self._update_color_previews()
        if announce:
            self.set_status(tr("palette.secondary_set", color=value))
        return "break"

    def _choose_palette_color(self, *, primary: bool) -> None:
        current = (
            self.foreground_color_value.get() if primary else self.background_color_value.get()
        )
        _rgb, selected = colorchooser.askcolor(
            color=current,
            parent=self.winfo_toplevel(),
            title=tr("palette.choose_primary" if primary else "palette.choose_secondary"),
        )
        if selected:
            if primary:
                self._set_primary_color(selected)
            else:
                self._set_secondary_color(selected)

    def swap_palette_colors(self) -> None:
        primary = self.foreground_color_value.get()
        secondary = self.background_color_value.get()
        self._set_primary_color(secondary, announce=False)
        self._set_secondary_color(primary, announce=False)
        self.set_status(tr("palette.swapped"))

    def reset_palette_colors(self) -> None:
        self._set_primary_color("#1C1714", announce=False)
        self._set_secondary_color("#F4E9D8", announce=False)
        self.set_status(tr("palette.reset"))

    def _sync_primary_from_brush(self, *_args: object) -> None:
        if self._syncing_color:
            return
        self.foreground_color_value.set(self.brush_color_value.get().upper())
        self._update_color_previews()

    def _sync_secondary_from_isen(self, *_args: object) -> None:
        if self._syncing_color:
            return
        self.background_color_value.set(self.motif_isen_color_value.get().upper())
        self._update_color_previews()

    def _update_color_previews(self) -> None:
        if self._primary_color_preview is not None and self._primary_color_preview.winfo_exists():
            color = self.foreground_color_value.get()
            self._primary_color_preview.configure(background=color, activebackground=color)
        if self._secondary_color_preview is not None and self._secondary_color_preview.winfo_exists():
            color = self.background_color_value.get()
            self._secondary_color_preview.configure(background=color, activebackground=color)

    def refresh_library(self) -> None:
        if not hasattr(self, "library_list") or not self.library_list.winfo_exists():
            return
        pack_display = self.library_pack_value.get()
        pack_id = self._library_pack_lookup.get(pack_display)
        category = self._category_display_to_id.get(self.library_category_value.get())
        try:
            records = self.asset_library.search(
                self.library_query_value.get(),
                category=category,
                pack_id=pack_id,
                limit=_MAX_VISIBLE_RESULTS,
            )
        except AssetLibraryError as exc:
            self.set_status(str(exc))
            return
        for item in self.library_list.get_children(""):
            self.library_list.delete(item)
        self._library_records.clear()
        pack_names = {pack.pack_id: pack.name for pack in self.asset_library.packs}
        for record in records:
            iid = record.key
            self._library_records[iid] = record
            self.library_list.insert(
                "",
                tk.END,
                iid=iid,
                text=record.name,
                values=(
                    category_label(record.category),
                    pack_names.get(record.pack_id, record.pack_id),
                ),
            )
        total = self.asset_library.asset_count
        suffix = "+" if len(records) == _MAX_VISIBLE_RESULTS and total > len(records) else ""
        self.library_summary_value.set(
            tr(
                "library.summary",
                shown=len(records),
                suffix=suffix,
                total=total,
                packs=len(self.asset_library.packs),
            )
        )
        self._refresh_pack_combo()

    def _refresh_pack_combo(self) -> None:
        if not hasattr(self, "library_pack_combo") or not self.library_pack_combo.winfo_exists():
            return
        current = self.library_pack_value.get()
        self._library_pack_lookup = {pack.name: pack.pack_id for pack in self.asset_library.packs}
        values = (self._all_packs_label, *self._library_pack_lookup)
        self.library_pack_combo.configure(values=values)
        if current not in values:
            self.library_pack_value.set(self._all_packs_label)

    def reload_asset_library(self) -> None:
        self.asset_library.refresh()
        self.refresh_library()
        self.set_status(tr("library.reloaded", count=self.asset_library.asset_count))

    def install_asset_pack_dialog(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title=tr("library.install_title"),
            filetypes=(("BatikCraft asset pack", f"*{ASSET_PACK_EXTENSION}"),),
        )
        if not selected:
            return
        try:
            pack = self.asset_library.install_pack(selected)
        except AssetLibraryError as exc:
            if "sudah terpasang" not in str(exc):
                messagebox.showerror(
                    tr("library.install_error"),
                    str(exc),
                    parent=self.winfo_toplevel(),
                )
                return
            replace = messagebox.askyesno(
                tr("library.replace_title"),
                tr("library.replace_question", error=exc),
                parent=self.winfo_toplevel(),
            )
            if not replace:
                return
            try:
                pack = self.asset_library.install_pack(selected, replace=True)
            except AssetLibraryError as replace_exc:
                messagebox.showerror(
                    tr("library.install_error"),
                    str(replace_exc),
                    parent=self.winfo_toplevel(),
                )
                return
        self.refresh_library()
        self.library_pack_value.set(pack.name)
        self.set_status(tr("library.installed", name=pack.name, count=len(pack.assets)))

    def uninstall_selected_pack(self) -> None:
        display = self.library_pack_value.get()
        pack_id = self._library_pack_lookup.get(display)
        if pack_id is None:
            self.set_status(tr("library.select_pack_first"))
            return
        pack = self.asset_library.get_pack(pack_id)
        if not messagebox.askyesno(
            tr("library.remove_title"),
            tr("library.remove_question", name=pack.name, count=len(pack.assets)),
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            self.asset_library.uninstall_pack(pack_id)
        except AssetLibraryError as exc:
            messagebox.showerror(
                tr("library.remove_error"),
                str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        self.library_pack_value.set(self._all_packs_label)
        self.refresh_library()
        self.set_status(tr("library.removed", name=pack.name))

    def add_selected_library_asset(self) -> None:
        if not self.session.has_project:
            self.set_status(tr("library.project_required"))
            return
        selection = self.library_list.selection()
        if not selection:
            self.set_status(tr("library.select_asset_first"))
            return
        record = self._library_records.get(selection[0])
        if record is None:
            self.set_status(tr("library.asset_missing"))
            return
        try:
            content = self.asset_library.read_asset(record)
            target = self._target_layer_for_object("assets", tr("library.target_layer"))
            item = self._object_session.import_batik_asset(
                Path(record.relative_path).name,
                content,
                target_layer_id=target.layer_id,
                default_category=record.category,
            )
        except (AssetLibraryError, ProjectSessionError, BatikAssetError, OSError) as exc:
            messagebox.showerror(
                tr("library.add_error"),
                str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh_context()
        self.set_status(tr("library.added", name=item.name))

    def _on_library_select(self, _event: tk.Event[ttk.Treeview]) -> None:
        selection = self.library_list.selection()
        if not selection:
            return
        record = self._library_records.get(selection[0])
        if record is None:
            return
        pack = self.asset_library.get_pack(record.pack_id)
        dimensions = (
            f"{record.width}×{record.height}px"
            if record.width and record.height
            else tr("common.file_size")
        )
        tags = ", ".join(record.tags[:5]) or tr("common.no_tags")
        self.library_asset_name_value.set(record.name)
        self.library_asset_meta_value.set(
            f"{category_label(record.category)} · {dimensions}\n{pack.name}\n{tags}"
        )
        self._show_library_preview(record)

    def _show_library_preview(self, record: AssetRecord) -> None:
        try:
            content = self.asset_library.read_thumbnail(record)
            if content is None:
                asset = load_batik_asset(
                    self.asset_library.read_asset(record),
                    filename=record.relative_path,
                    default_category=record.category,
                )
                content = asset.content
            with Image.open(BytesIO(content)) as source:
                source.load()
                image = source.convert("RGBA")
            image.thumbnail((92, 92), Image.Resampling.LANCZOS)
            self._library_preview_photo = ImageTk.PhotoImage(image)
            self.library_preview_label.configure(image=self._library_preview_photo, text="")
        except (
            AssetLibraryError,
            BatikAssetError,
            OSError,
            UnidentifiedImageError,
            ValueError,
        ):
            self._library_preview_photo = None
            self.library_preview_label.configure(
                image="",
                text=tr("library.preview_unavailable"),
            )

    def focus_asset_library(self) -> None:
        if not self.asset_panel.is_docked:
            self.asset_panel.undock()
        self.library_list.focus_set()
        self.set_status(tr("library.focused"))

    def open_brush_settings(self) -> None:
        self.tool_windows.open_brush("brush")

    def open_eraser_settings(self) -> None:
        self.tool_windows.open_brush("eraser")

    def open_shape_settings(self, shape_type: str) -> None:
        self.tool_windows.open_shape(shape_type)

    def open_motif_settings(self) -> None:
        self.tool_windows.open_motif()

    def open_isen_settings(self) -> None:
        self.tool_windows.open_isen()

    def open_transform_settings(self) -> None:
        self.tool_windows.open_transform()

    def open_asset_metadata_settings(self) -> None:
        self.tool_windows.open_asset_metadata()

    def open_humanize_settings(self) -> None:
        self.tool_windows.open_humanize()

    def new_folder(self) -> None:
        self._new_folder()

    def new_object_layer(self) -> None:
        self._new_object_layer()

    def new_paint_layer(self) -> None:
        self._new_paint_layer_in_tree()

    def _bind_compact_shortcuts(self) -> None:
        bindings: tuple[tuple[str, Callable[[], object]], ...] = (
            ("<Key-v>", self.activate_select_tool),
            ("<Key-b>", self.open_brush_settings),
            ("<Key-e>", self.open_eraser_settings),
            ("<Key-l>", lambda: self.open_shape_settings("line")),
            ("<Key-r>", lambda: self.open_shape_settings("rectangle")),
            ("<Key-o>", lambda: self.open_shape_settings("ellipse")),
            ("<Key-p>", lambda: self.open_shape_settings("polygon")),
            ("<Key-m>", self.open_motif_settings),
            ("<Key-c>", self.open_isen_settings),
        )
        for sequence, command in bindings:
            self.bind_all(
                sequence,
                lambda event, action=command: run_single_key_shortcut(event, action),
            )

    def destroy(self) -> None:
        if hasattr(self, "tool_windows"):
            self.tool_windows.close_all()
        for panel in self._dock_panels.values():
            panel.close()
        super().destroy()


__all__ = ["CompactAssetEditorWorkspaceView"]
