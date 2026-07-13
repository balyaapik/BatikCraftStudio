"""Compact native editor layout built on the stable raster-layer editor logic."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .layer_editor import LayerEditorWorkspaceView
from .theme import COLORS
from .widgets import icon_button


class NativeLayerEditorWorkspaceView(LayerEditorWorkspaceView):
    """Present the existing editor behavior in a compact desktop-design layout."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.configure(padding=0)

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        toolbox = ttk.Frame(self, style="Toolbar.TFrame", width=42, padding=(3, 4))
        toolbox.grid(row=0, column=0, sticky="ns")
        toolbox.grid_propagate(False)
        toolbox.columnconfigure(0, weight=1)
        icon_button(
            toolbox,
            icon="select",
            tooltip="Select and move objects",
            command=lambda: self.set_status("Select tool active"),
            style="ToolActive.TButton",
            size=20,
        ).grid(row=0, column=0, sticky="ew", pady=1)
        icon_button(
            toolbox,
            icon="import",
            tooltip="Import image (Ctrl+I)",
            command=self.import_image_dialog,
            size=20,
        ).grid(row=1, column=0, sticky="ew", pady=1)

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
        body.add(dock, weight=1)

    def _build_layer_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Layer stack", style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            sticky="ew",
        )
        self.layer_list = tk.Listbox(
            parent,
            activestyle="none",
            background=COLORS["white"],
            foreground=COLORS["ink"],
            selectbackground=COLORS["accent_soft"],
            selectforeground=COLORS["ink"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
            borderwidth=0,
            exportselection=False,
            font=("Segoe UI", 9),
        )
        self.layer_list.grid(row=1, column=0, sticky="nsew", pady=(4, 5))
        self.layer_list.bind("<<ListboxSelect>>", self._on_layer_list_select)

        controls = ttk.Frame(parent, style="Toolbar.TFrame", padding=(3, 3))
        controls.grid(row=2, column=0, sticky="ew")
        for icon, tooltip, command in (
            ("visibility", "Show or hide selected layer", self.toggle_visibility),
            ("lock", "Lock or unlock selected layer", self.toggle_lock),
            ("up", "Move selected layer up", self.move_active_up),
            ("down", "Move selected layer down", self.move_active_down),
            ("duplicate", "Duplicate selected layer", self.duplicate_active),
            ("delete", "Delete selected layer", self.delete_active),
        ):
            icon_button(
                controls,
                icon=icon,
                tooltip=tooltip,
                command=command,
                size=18,
            ).pack(side="left", padx=1)

    def _build_transform_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Dock.TFrame")
        panel.grid(row=0, column=0, sticky="new")
        panel.columnconfigure(1, weight=1)
        ttk.Label(panel, text="Object transform", style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 5),
        )
        fields = (
            ("X", self.x_value),
            ("Y", self.y_value),
            ("Rotation", self.rotation_value),
            ("Scale X", self.scale_x_value),
            ("Scale Y", self.scale_y_value),
            ("Opacity", self.opacity_value),
        )
        for row, (label, variable) in enumerate(fields, start=1):
            ttk.Label(panel, text=label, style="Muted.TLabel").grid(
                row=row,
                column=0,
                sticky="w",
                pady=3,
            )
            ttk.Entry(panel, textvariable=variable, width=12).grid(
                row=row,
                column=1,
                sticky="ew",
                padx=(8, 0),
                pady=3,
            )

        action_bar = ttk.Frame(panel, style="Toolbar.TFrame", padding=(3, 3))
        action_bar.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="e", pady=(8, 0))
        icon_button(
            action_bar,
            icon="apply",
            tooltip="Apply transform values",
            command=self.apply_transform,
            size=19,
        ).pack(side="right")
