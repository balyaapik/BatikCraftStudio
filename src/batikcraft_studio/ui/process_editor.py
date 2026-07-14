"""Right-click grouping and Batik production planning UI."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.application import BatikProcessProjectSession
from batikcraft_studio.i18n import tr

from .multi_object_editor import MultiObjectEditorWorkspaceView
from .process_dialog import BatikProcessStudioWindow


class BatikProcessEditorWorkspaceView(MultiObjectEditorWorkspaceView):
    """Keep marquee selection passive and expose grouping from a context menu."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._process_window: BatikProcessStudioWindow | None = None
        super().__init__(*args, **kwargs)
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
            label=tr("multi.context.process"),
            command=self.open_batik_process_studio,
        )
        self.canvas.bind("<Button-3>", self._show_selection_context_menu, add="+")

    def open_batik_process_studio(self) -> None:
        window = self._process_window
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            return
        self._process_window = BatikProcessStudioWindow(self, self._process_session)

    def _show_selection_context_menu(self, event: tk.Event[tk.Canvas]) -> str | None:
        if self._ai_selection_active or self._active_tool != "select":
            return None
        point = self._project_point(event.x, event.y)
        if point is None or self.session.project is None:
            return None
        hit = self._hit_topmost_object(point)
        selected_ids = self._process_session.selected_object_ids
        if hit is not None and hit.object_id not in selected_ids:
            self._process_session.select_object_for_editing(hit.object_id)
            self._refresh_multi_selection()
        selected = self._process_session.selected_objects
        if not selected:
            return None
        group_ids = {
            str(item.properties["object_group_id"])
            for item in selected
            if item.properties.get("object_group_id")
        }
        same_existing_group = (
            len(group_ids) == 1
            and all(item.properties.get("object_group_id") in group_ids for item in selected)
        )
        self._selection_context_menu.entryconfigure(
            0,
            state=(tk.NORMAL if len(selected) >= 2 and not same_existing_group else tk.DISABLED),
        )
        self._selection_context_menu.entryconfigure(
            1,
            state=(tk.NORMAL if group_ids else tk.DISABLED),
        )
        try:
            self._selection_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._selection_context_menu.grab_release()
        return "break"

    @property
    def _process_session(self) -> BatikProcessProjectSession:
        if not isinstance(self.session, BatikProcessProjectSession):
            raise RuntimeError("Editor proses memerlukan BatikProcessProjectSession.")
        return self.session


__all__ = ["BatikProcessEditorWorkspaceView"]
