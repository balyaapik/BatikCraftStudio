"""Rectangle selection and offline model workflows for the Batik canvas."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.application import OfflineAIProjectSession, ProjectSessionError
from batikcraft_studio.i18n import tr

from .offline_ai_dialogs import DatasetStudioWindow, OfflineModelManagerWindow
from .structured_batification_editor import StructuredBatificationEditorWorkspaceView


class OfflineAIEditorWorkspaceView(StructuredBatificationEditorWorkspaceView):
    """Add prompt-driven rectangle selection and local model management."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._ai_selection_active = False
        self._ai_selection_start_project: tuple[float, float] | None = None
        self._ai_selection_start_screen: tuple[int, int] | None = None
        self._ai_selection_rectangle: int | None = None
        self._dataset_window: DatasetStudioWindow | None = None
        self._model_window: OfflineModelManagerWindow | None = None
        super().__init__(*args, **kwargs)

    def open_dataset_studio(self) -> None:
        window = self._dataset_window
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            return
        self._dataset_window = DatasetStudioWindow(self)

    def open_offline_model_manager(self) -> None:
        window = self._model_window
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            return
        self._model_window = OfflineModelManagerWindow(
            self,
            self._offline_session,
            on_change=self._announce_provider,
        )

    def begin_ai_rectangle_selection(self) -> None:
        if self.session.project is None:
            self.set_status(tr("library.project_required"))
            return
        self._cancel_ai_selection()
        self._ai_selection_active = True
        self.canvas.configure(cursor="crosshair")
        self.set_status(tr("offline.selection.instructions"))

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if not self._ai_selection_active:
            super()._on_canvas_press(event)
            return
        point = self._project_point(event.x, event.y)
        if point is None:
            return
        self._ai_selection_start_project = point
        self._ai_selection_start_screen = (event.x, event.y)
        if self._ai_selection_rectangle is not None:
            self.canvas.delete(self._ai_selection_rectangle)
        self._ai_selection_rectangle = self.canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#2F6FED",
            width=2,
            dash=(6, 3),
        )

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if not self._ai_selection_active:
            super()._on_canvas_drag(event)
            return
        start = self._ai_selection_start_screen
        rectangle = self._ai_selection_rectangle
        if start is None or rectangle is None:
            return
        self.canvas.coords(rectangle, start[0], start[1], event.x, event.y)

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        if not self._ai_selection_active:
            super()._on_canvas_release(event)
            return
        start = self._ai_selection_start_project
        end = self._project_point(event.x, event.y)
        self._finish_ai_selection_visuals()
        if start is None or end is None:
            self.set_status(tr("offline.selection.cancelled"))
            return
        request = self._request_dialog("selection")
        if request is None:
            self.set_status(tr("offline.selection.cancelled"))
            return
        try:
            generation = self._offline_session.batify_rectangle_selection(
                (start[0], start[1], end[0], end[1]),
                request=request,
                name=tr("offline.selection.source_name"),
            )
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self._refresh_after_batification()
        self.set_status(
            tr(
                "offline.selection.rendered",
                version=generation.version,
                provider=generation.provider_id,
            )
        )

    def _cancel_ai_selection(self) -> None:
        if not self._ai_selection_active and self._ai_selection_rectangle is None:
            return
        self._finish_ai_selection_visuals()
        self.set_status(tr("offline.selection.cancelled"))

    def _finish_ai_selection_visuals(self) -> None:
        if self._ai_selection_rectangle is not None:
            self.canvas.delete(self._ai_selection_rectangle)
        self._ai_selection_rectangle = None
        self._ai_selection_start_project = None
        self._ai_selection_start_screen = None
        self._ai_selection_active = False
        self.canvas.configure(cursor="arrow")

    def _announce_provider(self) -> None:
        self.set_status(
            tr(
                "offline.models.provider_status",
                provider=self._offline_session.batification_provider_id,
            )
        )

    @property
    def _offline_session(self) -> OfflineAIProjectSession:
        if not isinstance(self.session, OfflineAIProjectSession):
            raise RuntimeError("Editor AI offline memerlukan OfflineAIProjectSession.")
        return self.session


__all__ = ["OfflineAIEditorWorkspaceView"]
