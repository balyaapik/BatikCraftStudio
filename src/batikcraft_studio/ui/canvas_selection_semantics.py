"""Desktop-style canvas selection and locked-object movement semantics.

Shift-click edits the current selection, dragging any unlocked selected object
moves every unlocked member together, and Ctrl+A selects every visible object
on the focused canvas. Locked objects may remain selected but never have their
transform changed by a collective move.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

from batikcraft_studio.application import MultiObjectProjectSession, ProjectSessionError
from batikcraft_studio.domain import LayerNodeKind, ObjectNotFoundError, Project

from .keyboard import event_targets_text_input
from .multi_object_editor import MultiObjectEditorWorkspaceView

_INSTALLED = False
_SHIFT_MASK = 0x0001


def install_canvas_selection_semantics() -> None:
    """Install desktop selection shortcuts after the renderer drag patches."""

    global _INSTALLED
    if _INSTALLED:
        return
    _patch_multi_object_session()
    _patch_multi_object_workspace()
    _INSTALLED = True


def _patch_multi_object_session() -> None:
    cls = MultiObjectProjectSession
    original_commit = cls.commit_interactive_multi_move
    original_cancel = cls.cancel_interactive_multi_move

    def begin_unlocked_multi_move(
        self: MultiObjectProjectSession,
        object_ids: tuple[str, ...] | list[str] | None = None,
    ) -> tuple[Any, ...]:
        if self.interactive_transform_active:
            self.cancel_interactive_object_transform()
        if self._multi_move_before is not None:
            self.cancel_interactive_multi_move()

        ids = tuple(object_ids) if object_ids is not None else self.selected_object_ids
        if not ids:
            raise ProjectSessionError("Tidak ada objek yang dipilih.")

        project = self.require_project()
        object_map: dict[str, tuple[str, Any]] = {}
        layer_locked: dict[str, bool] = {}
        for layer in project.layers:
            if layer.node_kind is LayerNodeKind.GROUP:
                continue
            layer_locked[layer.layer_id] = project.is_layer_effectively_locked(layer.layer_id)
            for item in layer.objects:
                object_map[item.object_id] = (layer.layer_id, item)

        originals: dict[str, Any] = {}
        movable: list[Any] = []
        for object_id in ids:
            entry = object_map.get(str(object_id))
            if entry is None:
                raise ObjectNotFoundError(f"Object {object_id} was not found.")
            layer_id, item = entry
            if item.locked or layer_locked.get(layer_id, False):
                continue
            originals[item.object_id] = item.transform
            movable.append(item)

        if not originals:
            raise ProjectSessionError(
                "Semua objek yang dipilih terkunci dan tidak dapat dipindahkan."
            )

        self._multi_move_before = self._capture_state()
        self._multi_move_originals = originals
        self._inkscape_multi_delta = (0.0, 0.0)
        self._inkscape_multi_movable_ids = tuple(originals)
        if self._selected_object_ids:
            project.set_active_object(self._selected_object_ids[-1])
        return tuple(movable)

    def commit_unlocked_multi_move(self: MultiObjectProjectSession) -> bool:
        try:
            return original_commit(self)
        finally:
            self._inkscape_multi_movable_ids = ()

    def cancel_unlocked_multi_move(self: MultiObjectProjectSession) -> bool:
        try:
            return original_cancel(self)
        finally:
            self._inkscape_multi_movable_ids = ()

    cls.begin_interactive_multi_move = begin_unlocked_multi_move
    cls.commit_interactive_multi_move = commit_unlocked_multi_move
    cls.cancel_interactive_multi_move = cancel_unlocked_multi_move


def _patch_multi_object_workspace() -> None:
    cls = MultiObjectEditorWorkspaceView
    original_init = cls.__init__
    original_press = cls._on_canvas_press
    original_begin_proxy = cls._begin_inkscape_multi_proxy

    def optimized_init(
        self: MultiObjectEditorWorkspaceView,
        *args: object,
        **kwargs: object,
    ) -> None:
        original_init(self, *args, **kwargs)
        for sequence in ("<Control-a>", "<Control-A>", "<Command-a>", "<Command-A>"):
            self.canvas.bind(sequence, self._select_all_canvas_objects, add="+")

    def optimized_press(
        self: MultiObjectEditorWorkspaceView,
        event: tk.Event[tk.Canvas],
    ) -> None:
        try:
            self.canvas.focus_set()
        except tk.TclError:
            pass

        if self._ai_selection_active or self._active_tool != "select":
            original_press(self, event)
            return
        project = self.session.project
        point = self._project_point(event.x, event.y)
        if project is None or point is None or bool(event.state & _SHIFT_MASK):
            original_press(self, event)
            return

        hit = self._hit_topmost_object(point)
        if hit is None or not _object_is_effectively_locked(project, hit.object_id):
            original_press(self, event)
            return

        selected_ids = self._multi_session.selected_object_ids
        if hit.object_id not in selected_ids:
            self._multi_session.select_object_for_editing(hit.object_id)
            self._refresh_multi_selection()
        self.set_status(f"Objek {hit.name!r} terkunci dan tidak dapat dipindahkan.")

    def begin_movable_proxy(
        self: MultiObjectEditorWorkspaceView,
        pointer_screen: tuple[int, int],
    ) -> None:
        movable_ids = tuple(
            getattr(self._multi_session, "_inkscape_multi_movable_ids", ())
        )
        if not movable_ids:
            return

        project = self.session.require_project()
        selected_before = list(self._multi_session._selected_object_ids)
        active_before = project.active_object_id
        self._multi_session._selected_object_ids = list(movable_ids)
        project.set_active_object(movable_ids[-1])
        try:
            original_begin_proxy(self, pointer_screen)
        finally:
            self._multi_session._selected_object_ids = selected_before
            project.set_active_object(active_before)

    def select_all_canvas_objects(
        self: MultiObjectEditorWorkspaceView,
        event: tk.Event[tk.Misc],
    ) -> str | None:
        if event_targets_text_input(event):
            return None
        project = self.session.project
        if project is None:
            return "break"
        object_ids = _visible_canvas_object_ids(project)
        if object_ids:
            self._multi_session.set_selected_objects(list(object_ids), expand_groups=False)
        else:
            self._multi_session.clear_object_selection()
        self._refresh_multi_selection()
        self.set_status(f"{len(object_ids)} objek dipilih di canvas.")
        return "break"

    cls.__init__ = optimized_init
    cls._on_canvas_press = optimized_press
    cls._begin_inkscape_multi_proxy = begin_movable_proxy
    cls._select_all_canvas_objects = select_all_canvas_objects


def _visible_canvas_object_ids(project: Project) -> tuple[str, ...]:
    """Return every visible canvas object, including locked objects."""

    return tuple(
        item.object_id
        for layer in project.layers
        if layer.node_kind is not LayerNodeKind.GROUP
        and project.is_layer_effectively_visible(layer.layer_id)
        for item in layer.objects
        if item.visible
    )


def _object_is_effectively_locked(project: Project, object_id: str) -> bool:
    item = project.get_object(object_id)
    return item.locked or project.is_layer_effectively_locked(
        project.object_layer_id(object_id)
    )


__all__ = ["install_canvas_selection_semantics"]
