"""Canvas rulers, object-first layer context actions, and closed-shape fill UI."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import colorchooser

from batikcraft_studio.application import (
    CanvasStructureProjectSession,
    ProjectSessionError,
    ShapeLayerError,
)
from batikcraft_studio.domain import Layer, ObjectKind
from batikcraft_studio.i18n import tr

from .canvas_structure_i18n import install_canvas_structure_translations
from .process_editor import BatikProcessEditorWorkspaceView

install_canvas_structure_translations()

_RULER_HEIGHT = 24
_RULER_WIDTH = 46
_RULER_BACKGROUND = "#E7E2DA"
_RULER_INK = "#4A4540"
_RULER_GUIDE = "#2F6FED"


class CanvasStructureEditorWorkspaceView(BatikProcessEditorWorkspaceView):
    """Expose rulers and make canvas shapes regular objects inside layers."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._rulers_ready = False
        super().__init__(*args, **kwargs)
        self._install_canvas_rulers()
        self._build_structure_context_menu()
        self._rulers_ready = True
        self._draw_rulers()

    def apply_shape_properties(self) -> None:
        item = self._active_object()
        if item is None or item.kind is not ObjectKind.SHAPE:
            super().apply_shape_properties()
            return
        shape_type = str(item.properties.get("shape_type", ""))
        try:
            self._structure_session.update_shape_layer(
                item.object_id,
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
        self.set_status(tr("structure.shape.updated", name=item.name))

    def _refresh_transform_fields(self) -> None:
        super()._refresh_transform_fields()
        if not getattr(self, "_shape_widgets_ready", False):
            return
        item = self._active_object()
        if item is None or item.kind is not ObjectKind.SHAPE:
            return
        properties = item.properties
        shape_type = str(properties.get("shape_type", "shape"))
        self.shape_type_text.set(tr("structure.shape.selected", shape=shape_type.title()))
        self.shape_width_value.set(float(properties.get("geometry_width", 1.0)))
        self.shape_height_value.set(float(properties.get("geometry_height", 1.0)))
        self.shape_stroke_color.set(str(properties.get("stroke_color", "#273043")))
        self.shape_fill_color.set(str(properties.get("fill_color", "#D9A566")))
        self.shape_stroke_width.set(float(properties.get("stroke_width", 4.0)))
        self.shape_stroke_enabled.set(bool(properties.get("stroke_enabled", True)))
        self.shape_fill_enabled.set(bool(properties.get("fill_enabled", False)))
        self.shape_polygon_sides.set(int(properties.get("polygon_sides", 6)))
        if hasattr(self, "stroke_swatch"):
            self.stroke_swatch.configure(
                background=self.shape_stroke_color.get(),
                activebackground=self.shape_stroke_color.get(),
            )
        if hasattr(self, "fill_swatch"):
            self.fill_swatch.configure(
                background=self.shape_fill_color.get(),
                activebackground=self.shape_fill_color.get(),
            )

    def _new_default_shape(self, shape_type: str) -> None:
        if not self.session.has_project:
            self.set_status(tr("library.project_required"))
            return
        try:
            item = self._structure_session.create_default_shape_layer(
                shape_type,
                **self._shape_style(shape_type),
            )
        except (ShapeLayerError, ValueError) as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(tr("structure.shape.created", name=item.name))

    def _build_structure_context_menu(self) -> None:
        self._selection_context_menu = tk.Menu(self, tearoff=False)
        self._selection_context_menu.add_command(
            label=tr("multi.context.group"),
            command=self.group_selected_objects,
        )
        self._selection_context_menu.add_command(
            label=tr("multi.context.ungroup"),
            command=self.ungroup_selected_objects,
        )
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label=tr("structure.context.new_layer"),
            command=self._create_context_layer,
        )
        self._selection_context_menu.add_command(
            label=tr("structure.context.new_folder"),
            command=self._create_context_folder,
        )
        self._move_layer_menu = tk.Menu(self._selection_context_menu, tearoff=False)
        self._selection_context_menu.add_cascade(
            label=tr("structure.context.move_to_layer"),
            menu=self._move_layer_menu,
        )
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label=tr("structure.context.fill_color"),
            command=self._choose_selected_fill_color,
        )
        self._selection_context_menu.add_separator()
        self._selection_context_menu.add_command(
            label=tr("multi.context.process"),
            command=self.open_batik_process_studio,
        )

    def _show_selection_context_menu(self, event: tk.Event[tk.Canvas]) -> str | None:
        if self._ai_selection_active or self._active_tool != "select":
            return None
        point = self._project_point(event.x, event.y)
        project = self.session.project
        if point is None or project is None:
            return None
        hit = self._hit_topmost_object(point)
        selected_ids = self._structure_session.selected_object_ids
        if hit is not None and hit.object_id not in selected_ids:
            self._structure_session.select_object_for_editing(hit.object_id)
            self._refresh_multi_selection()
        selected = self._structure_session.selected_objects
        group_ids = {
            str(item.properties["object_group_id"])
            for item in selected
            if item.properties.get("object_group_id")
        }
        same_existing_group = (
            len(group_ids) == 1
            and bool(selected)
            and all(item.properties.get("object_group_id") in group_ids for item in selected)
        )
        closed_shapes = tuple(
            item for item in selected if self._structure_session.is_closed_shape(item)
        )
        self._populate_move_layer_menu()
        self._selection_context_menu.entryconfigure(
            0,
            state=(tk.NORMAL if len(selected) >= 2 and not same_existing_group else tk.DISABLED),
        )
        self._selection_context_menu.entryconfigure(
            1,
            state=(tk.NORMAL if group_ids else tk.DISABLED),
        )
        self._selection_context_menu.entryconfigure(
            5,
            state=(
                tk.NORMAL
                if selected and self._structure_session.object_layers
                else tk.DISABLED
            ),
        )
        self._selection_context_menu.entryconfigure(
            7,
            state=(tk.NORMAL if closed_shapes else tk.DISABLED),
        )
        try:
            self._selection_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._selection_context_menu.grab_release()
        return "break"

    def _populate_move_layer_menu(self) -> None:
        self._move_layer_menu.delete(0, tk.END)
        layers = self._structure_session.object_layers
        if not layers:
            self._move_layer_menu.add_command(
                label=tr("structure.context.no_layers"),
                state=tk.DISABLED,
            )
            return
        project = self.session.require_project()
        selected = self._structure_session.selected_objects
        current_layers = {
            project.object_layer_id(item.object_id) for item in selected
        }
        for layer in layers:
            self._move_layer_menu.add_command(
                label=self._layer_path(layer),
                state=(
                    tk.DISABLED
                    if current_layers == {layer.layer_id}
                    else tk.NORMAL
                ),
                command=lambda target=layer.layer_id: self._move_selection_to_layer(target),
            )

    def _layer_path(self, layer: Layer) -> str:
        project = self.session.require_project()
        names = [layer.name]
        parent_id = layer.parent_id
        visited: set[str] = set()
        while parent_id is not None and parent_id not in visited:
            visited.add(parent_id)
            parent = project.get_layer(parent_id)
            names.append(parent.name)
            parent_id = parent.parent_id
        return " / ".join(reversed(names))

    def _create_context_layer(self) -> None:
        layer = self._structure_session.create_layer_for_current_context()
        self.refresh_context()
        self.set_status(tr("structure.layer.created", name=layer.name))

    def _create_context_folder(self) -> None:
        folder = self._structure_session.create_folder_for_current_context()
        self.refresh_context()
        self.set_status(tr("structure.folder.created", name=folder.name))

    def _move_selection_to_layer(self, layer_id: str) -> None:
        try:
            moved = self._structure_session.move_selected_objects_to_layer(layer_id)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        layer = self.session.require_project().get_layer(layer_id)
        self.set_status(
            tr("structure.objects.moved", count=len(moved), layer=layer.name)
        )

    def _choose_selected_fill_color(self) -> None:
        closed = tuple(
            item
            for item in self._structure_session.selected_objects
            if self._structure_session.is_closed_shape(item)
        )
        if not closed:
            self.set_status(tr("structure.fill.closed_required"))
            return
        initial = str(closed[-1].properties.get("fill_color", "#D9A566"))
        _rgb, selected = colorchooser.askcolor(
            color=initial,
            parent=self.winfo_toplevel(),
            title=tr("structure.fill.choose"),
        )
        if not selected:
            return
        try:
            updated = self._structure_session.set_selected_closed_shape_fill(
                selected.upper()
            )
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(
            tr("structure.fill.applied", count=len(updated), color=selected.upper())
        )

    def _install_canvas_rulers(self) -> None:
        shell = self.canvas.master
        caption = next(iter(shell.grid_slaves(row=1, column=0)), None)
        shell.columnconfigure(0, weight=0, minsize=_RULER_WIDTH)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=0, minsize=_RULER_HEIGHT)
        shell.rowconfigure(1, weight=1)
        shell.rowconfigure(2, weight=0)
        self.canvas.grid_configure(row=1, column=1, sticky="nsew")
        if caption is not None:
            caption.grid_configure(row=2, column=1, sticky="ew")
        self._ruler_corner = tk.Canvas(
            shell,
            width=_RULER_WIDTH,
            height=_RULER_HEIGHT,
            background=_RULER_BACKGROUND,
            highlightthickness=0,
            borderwidth=0,
        )
        self._ruler_corner.grid(row=0, column=0, sticky="nsew")
        self.horizontal_ruler = tk.Canvas(
            shell,
            height=_RULER_HEIGHT,
            background=_RULER_BACKGROUND,
            highlightthickness=0,
            borderwidth=0,
        )
        self.horizontal_ruler.grid(row=0, column=1, sticky="ew")
        self.vertical_ruler = tk.Canvas(
            shell,
            width=_RULER_WIDTH,
            background=_RULER_BACKGROUND,
            highlightthickness=0,
            borderwidth=0,
        )
        self.vertical_ruler.grid(row=1, column=0, sticky="ns")
        self.horizontal_ruler.bind(
            "<Configure>", lambda _event: self._draw_rulers(), add="+"
        )
        self.vertical_ruler.bind(
            "<Configure>", lambda _event: self._draw_rulers(), add="+"
        )
        self.canvas.bind("<Configure>", lambda _event: self._draw_rulers(), add="+")
        self.canvas.bind("<Motion>", self._draw_ruler_pointer, add="+")
        self.canvas.bind("<Leave>", self._clear_ruler_pointer, add="+")

    def _render(self) -> None:
        super()._render()
        if self._rulers_ready:
            self._draw_rulers()

    def _draw_rulers(self) -> None:
        if not self._rulers_ready and not hasattr(self, "horizontal_ruler"):
            return
        horizontal = self.horizontal_ruler
        vertical = self.vertical_ruler
        horizontal.delete("all")
        vertical.delete("all")
        horizontal.create_line(
            0,
            _RULER_HEIGHT - 1,
            horizontal.winfo_width(),
            _RULER_HEIGHT - 1,
            fill="#B7B0A8",
        )
        vertical.create_line(
            _RULER_WIDTH - 1,
            0,
            _RULER_WIDTH - 1,
            vertical.winfo_height(),
            fill="#B7B0A8",
        )
        project = self.session.project
        scale = getattr(self, "_preview_scale", 0.0)
        if project is None or scale <= 0:
            horizontal.create_text(6, 4, text="px", anchor="nw", fill=_RULER_INK)
            return
        major = choose_ruler_step(scale)
        minor = major / 5
        self._draw_horizontal_ticks(project.canvas.width, scale, major, minor)
        self._draw_vertical_ticks(project.canvas.height, scale, major, minor)

    def _draw_horizontal_ticks(
        self,
        project_width: int,
        scale: float,
        major: float,
        minor: float,
    ) -> None:
        width = self.horizontal_ruler.winfo_width()
        count = int(math.floor(project_width / minor))
        for index in range(count + 1):
            value = index * minor
            x = self._preview_left + value * scale
            if x < 0 or x > width:
                continue
            is_major = index % 5 == 0
            tick_top = 10 if is_major else 17
            self.horizontal_ruler.create_line(
                x,
                tick_top,
                x,
                _RULER_HEIGHT,
                fill=_RULER_INK,
            )
            if is_major:
                self.horizontal_ruler.create_text(
                    x + 3,
                    2,
                    text=format_ruler_value(value),
                    anchor="nw",
                    fill=_RULER_INK,
                    font=("TkDefaultFont", 8),
                )

    def _draw_vertical_ticks(
        self,
        project_height: int,
        scale: float,
        major: float,
        minor: float,
    ) -> None:
        height = self.vertical_ruler.winfo_height()
        count = int(math.floor(project_height / minor))
        for index in range(count + 1):
            value = index * minor
            y = self._preview_top + value * scale
            if y < 0 or y > height:
                continue
            is_major = index % 5 == 0
            tick_left = 23 if is_major else 36
            self.vertical_ruler.create_line(
                tick_left,
                y,
                _RULER_WIDTH,
                y,
                fill=_RULER_INK,
            )
            if is_major:
                self.vertical_ruler.create_text(
                    2,
                    y + 2,
                    text=format_ruler_value(value),
                    anchor="nw",
                    fill=_RULER_INK,
                    font=("TkDefaultFont", 8),
                )

    def _draw_ruler_pointer(self, event: tk.Event[tk.Canvas]) -> None:
        if not self._rulers_ready:
            return
        self.horizontal_ruler.delete("ruler-pointer")
        self.vertical_ruler.delete("ruler-pointer")
        point = self._project_point(event.x, event.y)
        if point is None:
            return
        project = self.session.project
        if project is None or not (
            0 <= point[0] <= project.canvas.width
            and 0 <= point[1] <= project.canvas.height
        ):
            return
        self.horizontal_ruler.create_line(
            event.x,
            0,
            event.x,
            _RULER_HEIGHT,
            fill=_RULER_GUIDE,
            tags="ruler-pointer",
        )
        self.vertical_ruler.create_line(
            0,
            event.y,
            _RULER_WIDTH,
            event.y,
            fill=_RULER_GUIDE,
            tags="ruler-pointer",
        )

    def _clear_ruler_pointer(self, _event: tk.Event[tk.Canvas]) -> None:
        if not self._rulers_ready:
            return
        self.horizontal_ruler.delete("ruler-pointer")
        self.vertical_ruler.delete("ruler-pointer")

    @property
    def _structure_session(self) -> CanvasStructureProjectSession:
        if not isinstance(self.session, CanvasStructureProjectSession):
            raise RuntimeError(
                "Editor struktur canvas memerlukan CanvasStructureProjectSession."
            )
        return self.session


def choose_ruler_step(scale: float, minimum_screen_spacing: float = 70.0) -> float:
    """Choose a 1/2/5 ruler interval that stays readable at the current zoom."""

    if scale <= 0 or not math.isfinite(scale):
        return 100.0
    raw = max(1e-9, minimum_screen_spacing / scale)
    exponent = math.floor(math.log10(raw))
    magnitude = 10**exponent
    normalized = raw / magnitude
    if normalized <= 1:
        factor = 1
    elif normalized <= 2:
        factor = 2
    elif normalized <= 5:
        factor = 5
    else:
        factor = 10
    return float(factor * magnitude)


def format_ruler_value(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-8:
        return str(rounded)
    return f"{value:.1f}".rstrip("0").rstrip(".")


__all__ = [
    "CanvasStructureEditorWorkspaceView",
    "choose_ruler_step",
    "format_ruler_value",
]
