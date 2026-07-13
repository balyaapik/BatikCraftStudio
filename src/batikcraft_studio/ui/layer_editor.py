"""Tkinter raster-layer editor for Milestone 2D."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

from batikcraft_studio.application import LayerLockedError, ProjectSession, ProjectSessionError
from batikcraft_studio.config import WorkspaceDefinition
from batikcraft_studio.domain import Layer, ProjectValidationError
from batikcraft_studio.imaging import (
    ProjectRenderError,
    RasterImageError,
    point_hits_layer,
    render_project_preview,
    transformed_layer_bounds,
)

from .theme import COLORS

StatusCallback = Callable[[str], None]
RefreshCallback = Callable[[], None]


class LayerEditorWorkspaceView(ttk.Frame):
    """Render and edit image-backed layers without drawing tools or AI."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        definition: WorkspaceDefinition,
        set_status: StatusCallback,
        session: ProjectSession,
        refresh_context: RefreshCallback,
    ) -> None:
        super().__init__(parent, style="App.TFrame", padding=(24, 20))
        self.definition = definition
        self.set_status = set_status
        self.session = session
        self.refresh_context = refresh_context
        self.canvas_caption = tk.StringVar(value="No project open")
        self._photo: ImageTk.PhotoImage | None = None
        self._preview_scale = 1.0
        self._preview_left = 0.0
        self._preview_top = 0.0
        self._render_after_id: str | None = None
        self._layer_ids: list[str] = []
        self._updating_layer_list = False
        self._drag_layer_id: str | None = None
        self._drag_start: tuple[float, float] | None = None
        self._drag_origin: tuple[float, float] | None = None
        self._drag_last: tuple[float, float] | None = None

        self.x_value = tk.StringVar()
        self.y_value = tk.StringVar()
        self.rotation_value = tk.StringVar()
        self.scale_x_value = tk.StringVar()
        self.scale_y_value = tk.StringVar()
        self.opacity_value = tk.StringVar()

        self._build()
        self.refresh_project()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build_header()
        self._build_toolbar()

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.grid(row=2, column=0, sticky="nsew")

        canvas_shell = ttk.Frame(body, style="Surface.TFrame", padding=10)
        canvas_shell.columnconfigure(0, weight=1)
        canvas_shell.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            canvas_shell,
            background=COLORS["surface_alt"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
            cursor="arrow",
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self._schedule_render())
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        body.add(canvas_shell, weight=4)

        inspector = ttk.Frame(body, style="Surface.TFrame", padding=(16, 14), width=300)
        inspector.grid_propagate(False)
        inspector.columnconfigure(0, weight=1)
        inspector.rowconfigure(2, weight=1)
        self._build_layer_panel(inspector)
        self._build_transform_panel(inspector)
        body.add(inspector, weight=1)

    def _build_header(self) -> None:
        header = ttk.Frame(self, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=self.definition.eyebrow, style="Eyebrow.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Label(header, text=self.definition.title, style="Title.TLabel").grid(
            row=1,
            column=0,
            sticky="w",
            pady=(3, 0),
        )
        ttk.Label(
            header,
            textvariable=self.canvas_caption,
            style="Description.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

    def _build_toolbar(self) -> None:
        tools = ttk.Frame(self, style="Surface.TFrame", padding=(12, 9))
        tools.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        buttons = (
            ("Import Image", self.import_image_dialog),
            ("Undo", self.undo),
            ("Redo", self.redo),
            ("Duplicate", self.duplicate_active),
            ("Delete", self.delete_active),
        )
        for index, (label, command) in enumerate(buttons):
            ttk.Button(
                tools,
                text=label,
                style="Primary.TButton" if index == 0 else "Secondary.TButton",
                command=command,
            ).pack(side="left", padx=(0, 8))
        ttk.Label(
            tools,
            text="Click a layer to select it. Drag an unlocked layer to move it.",
            style="CardText.TLabel",
        ).pack(side="right")

    def _build_layer_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Layers", style="CardTitle.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.layer_list = tk.Listbox(
            parent,
            activestyle="none",
            background=COLORS["surface"],
            foreground=COLORS["ink"],
            selectbackground=COLORS["accent_soft"],
            selectforeground=COLORS["ink"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
            borderwidth=0,
            exportselection=False,
            font=("Segoe UI", 10),
        )
        self.layer_list.grid(row=1, column=0, sticky="nsew", pady=(8, 8))
        self.layer_list.bind("<<ListboxSelect>>", self._on_layer_list_select)

        controls = ttk.Frame(parent, style="Surface.TFrame")
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        controls.columnconfigure((0, 1), weight=1)
        layer_buttons = (
            ("Show/Hide", self.toggle_visibility),
            ("Lock/Unlock", self.toggle_lock),
            ("Move Up", self.move_active_up),
            ("Move Down", self.move_active_down),
        )
        for index, (label, command) in enumerate(layer_buttons):
            ttk.Button(
                controls,
                text=label,
                style="Secondary.TButton",
                command=command,
            ).grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=(0, 4) if index % 2 == 0 else (4, 0),
                pady=3,
            )

    def _build_transform_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Transform", padding=(10, 8))
        panel.grid(row=3, column=0, sticky="ew")
        panel.columnconfigure(1, weight=1)
        fields = (
            ("X", self.x_value),
            ("Y", self.y_value),
            ("Rotation", self.rotation_value),
            ("Scale X", self.scale_x_value),
            ("Scale Y", self.scale_y_value),
            ("Opacity", self.opacity_value),
        )
        for row, (label, variable) in enumerate(fields):
            ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(panel, textvariable=variable, width=13).grid(
                row=row,
                column=1,
                sticky="ew",
                padx=(8, 0),
                pady=3,
            )
        ttk.Button(
            panel,
            text="Apply Transform",
            style="Primary.TButton",
            command=self.apply_transform,
        ).grid(row=len(fields), column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def refresh_project(self) -> None:
        snapshot = self.session.snapshot()
        if not snapshot.has_project:
            self.canvas_caption.set("Create or open a project, then import a PNG or JPEG image.")
        else:
            state = "Unsaved changes" if snapshot.dirty else "Saved"
            self.canvas_caption.set(
                f"{snapshot.title} • {snapshot.width} × {snapshot.height}px • "
                f"{snapshot.layer_count} layers • {state}"
            )
        self._refresh_layer_list()
        self._refresh_transform_fields()
        self._schedule_render()

    def import_image_dialog(self) -> None:
        if not self.session.has_project:
            self.set_status("Create or open a project before importing an image.")
            return
        selected = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Import Raster Layer",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg"),
                ("PNG image", "*.png"),
                ("JPEG image", "*.jpg *.jpeg"),
            ),
        )
        if not selected:
            return
        path = Path(selected)
        try:
            layer = self.session.import_raster_image(path.name, path.read_bytes())
        except (OSError, RasterImageError, ProjectSessionError, ProjectValidationError) as exc:
            messagebox.showerror(
                "Could not import image",
                str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh_context()
        self.set_status(f"Imported raster layer: {layer.name}")

    def undo(self) -> None:
        if self.session.undo():
            self.refresh_context()
            self.set_status("Undid the last layer edit.")
        else:
            self.set_status("Nothing to undo.")

    def redo(self) -> None:
        if self.session.redo():
            self.refresh_context()
            self.set_status("Redid the last layer edit.")
        else:
            self.set_status("Nothing to redo.")

    def duplicate_active(self) -> None:
        layer = self._active_layer()
        if layer is None:
            self.set_status("Select a layer to duplicate.")
            return
        duplicate = self.session.duplicate_layer(layer.layer_id)
        self.refresh_context()
        self.set_status(f"Duplicated layer: {duplicate.name}")

    def delete_active(self) -> None:
        layer = self._active_layer()
        if layer is None:
            self.set_status("Select a layer to delete.")
            return
        try:
            removed = self.session.delete_layer(layer.layer_id)
        except LayerLockedError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(f"Deleted layer: {removed.name}")

    def toggle_visibility(self) -> None:
        layer = self._active_layer()
        if layer is None:
            self.set_status("Select a layer first.")
            return
        self.session.set_layer_visibility(layer.layer_id, not layer.visible)
        self.refresh_context()

    def toggle_lock(self) -> None:
        layer = self._active_layer()
        if layer is None:
            self.set_status("Select a layer first.")
            return
        self.session.set_layer_locked(layer.layer_id, not layer.locked)
        self.refresh_context()

    def move_active_up(self) -> None:
        layer = self._active_layer()
        if layer is None or not self.session.move_layer_up(layer.layer_id):
            self.set_status("The selected layer is already at the top.")
            return
        self.refresh_context()

    def move_active_down(self) -> None:
        layer = self._active_layer()
        if layer is None or not self.session.move_layer_down(layer.layer_id):
            self.set_status("The selected layer is already at the bottom.")
            return
        self.refresh_context()

    def apply_transform(self) -> None:
        layer = self._active_layer()
        if layer is None:
            self.set_status("Select a layer before applying a transform.")
            return
        try:
            self.session.update_layer_transform(
                layer.layer_id,
                x=float(self.x_value.get()),
                y=float(self.y_value.get()),
                rotation_degrees=float(self.rotation_value.get()),
                scale_x=float(self.scale_x_value.get()),
                scale_y=float(self.scale_y_value.get()),
            )
            self.session.set_layer_opacity(layer.layer_id, float(self.opacity_value.get()))
        except (ValueError, LayerLockedError, ProjectValidationError) as exc:
            messagebox.showerror(
                "Invalid transform",
                str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh_context()
        self.set_status(f"Updated transform: {layer.name}")

    def _refresh_layer_list(self) -> None:
        self._updating_layer_list = True
        self.layer_list.delete(0, tk.END)
        self._layer_ids = []
        project = self.session.project
        if project is not None:
            for layer in reversed(project.layers):
                visible = "V" if layer.visible else "-"
                locked = "L" if layer.locked else "-"
                self.layer_list.insert(tk.END, f"[{visible}{locked}] {layer.name}")
                self._layer_ids.append(layer.layer_id)
            if project.active_layer_id in self._layer_ids:
                index = self._layer_ids.index(project.active_layer_id)
                self.layer_list.selection_set(index)
                self.layer_list.see(index)
        self._updating_layer_list = False

    def _refresh_transform_fields(self) -> None:
        layer = self._active_layer()
        values = ("", "", "", "", "", "")
        if layer is not None:
            values = (
                _format_number(layer.transform.x),
                _format_number(layer.transform.y),
                _format_number(layer.transform.rotation_degrees),
                _format_number(layer.transform.scale_x),
                _format_number(layer.transform.scale_y),
                _format_number(layer.opacity),
            )
        for variable, value in zip(
            (
                self.x_value,
                self.y_value,
                self.rotation_value,
                self.scale_x_value,
                self.scale_y_value,
                self.opacity_value,
            ),
            values,
            strict=True,
        ):
            variable.set(value)

    def _on_layer_list_select(self, _event: tk.Event[tk.Misc]) -> None:
        if self._updating_layer_list:
            return
        selection = self.layer_list.curselection()
        if not selection:
            return
        layer_id = self._layer_ids[selection[0]]
        self.session.select_layer(layer_id)
        self._refresh_transform_fields()
        self._draw_selection()

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        project = self.session.project
        if project is None or self._preview_scale <= 0:
            return
        project_x = (event.x - self._preview_left) / self._preview_scale
        project_y = (event.y - self._preview_top) / self._preview_scale
        selected: Layer | None = None
        for layer in reversed(project.layers):
            if layer.visible and layer.asset_ref is not None and point_hits_layer(
                layer,
                project_x,
                project_y,
            ):
                selected = layer
                break
        if selected is None:
            self.session.select_layer(None)
            self._refresh_layer_list()
            self._refresh_transform_fields()
            self._draw_selection()
            return

        self.session.select_layer(selected.layer_id)
        self._refresh_layer_list()
        self._refresh_transform_fields()
        self._draw_selection()
        if not selected.locked:
            self._drag_layer_id = selected.layer_id
            self._drag_start = (event.x, event.y)
            self._drag_last = (event.x, event.y)
            self._drag_origin = (selected.transform.x, selected.transform.y)
            self.canvas.configure(cursor="fleur")

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self._drag_layer_id is None or self._drag_last is None:
            return
        delta_x = event.x - self._drag_last[0]
        delta_y = event.y - self._drag_last[1]
        self.canvas.move("selection", delta_x, delta_y)
        self._drag_last = (event.x, event.y)

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        if (
            self._drag_layer_id is None
            or self._drag_start is None
            or self._drag_origin is None
            or self._preview_scale <= 0
        ):
            self._clear_drag()
            return
        delta_x = (event.x - self._drag_start[0]) / self._preview_scale
        delta_y = (event.y - self._drag_start[1]) / self._preview_scale
        try:
            self.session.move_layer(
                self._drag_layer_id,
                x=self._drag_origin[0] + delta_x,
                y=self._drag_origin[1] + delta_y,
            )
        except (LayerLockedError, ProjectValidationError) as exc:
            self.set_status(str(exc))
        self._clear_drag()
        self.refresh_context()

    def _clear_drag(self) -> None:
        self._drag_layer_id = None
        self._drag_start = None
        self._drag_origin = None
        self._drag_last = None
        self.canvas.configure(cursor="arrow")

    def _schedule_render(self) -> None:
        if self._render_after_id is not None:
            self.after_cancel(self._render_after_id)
        self._render_after_id = self.after(35, self._render)

    def _render(self) -> None:
        self._render_after_id = None
        self.canvas.delete("all")
        project = self.session.project
        width = max(self.canvas.winfo_width(), 40)
        height = max(self.canvas.winfo_height(), 40)
        if project is None:
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="Create or open a BatikCraft project to begin.",
                fill=COLORS["muted_ink"],
                font=("Segoe UI", 14),
            )
            return
        try:
            rendered = render_project_preview(
                project,
                self.session.assets,
                max_width=max(width - 70, 1),
                max_height=max(height - 70, 1),
            )
        except ProjectRenderError as exc:
            self.canvas.create_text(
                width / 2,
                height / 2,
                text=str(exc),
                fill=COLORS["warning"],
                width=max(width - 80, 100),
                justify="center",
            )
            return

        self._preview_scale = rendered.scale
        self._preview_left = (width - rendered.image.width) / 2
        self._preview_top = (height - rendered.image.height) / 2
        self.canvas.create_rectangle(
            self._preview_left + 7,
            self._preview_top + 7,
            self._preview_left + rendered.image.width + 7,
            self._preview_top + rendered.image.height + 7,
            fill="#C9C0B3",
            outline="",
        )
        self._photo = ImageTk.PhotoImage(rendered.image)
        self.canvas.create_image(
            self._preview_left,
            self._preview_top,
            image=self._photo,
            anchor="nw",
        )
        self._draw_selection()

    def _draw_selection(self) -> None:
        self.canvas.delete("selection")
        layer = self._active_layer()
        if layer is None or layer.asset_ref is None or not layer.visible:
            return
        try:
            left, top, right, bottom = transformed_layer_bounds(
                layer,
                preview_scale=self._preview_scale,
            )
        except ProjectRenderError:
            return
        color = COLORS["warning"] if layer.locked else COLORS["accent_dark"]
        coordinates = (
            self._preview_left + left,
            self._preview_top + top,
            self._preview_left + right,
            self._preview_top + bottom,
        )
        self.canvas.create_rectangle(
            *coordinates,
            outline=color,
            width=2,
            dash=(5, 3),
            tags="selection",
        )
        for x, y in (
            (coordinates[0], coordinates[1]),
            (coordinates[2], coordinates[1]),
            (coordinates[0], coordinates[3]),
            (coordinates[2], coordinates[3]),
        ):
            self.canvas.create_rectangle(
                x - 4,
                y - 4,
                x + 4,
                y + 4,
                fill=color,
                outline=COLORS["white"],
                tags="selection",
            )

    def _active_layer(self) -> Layer | None:
        project = self.session.project
        if project is None or project.active_layer_id is None:
            return None
        return project.get_layer(project.active_layer_id)


def _format_number(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")
