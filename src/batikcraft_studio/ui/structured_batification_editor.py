"""Structured Batification commands for the professional canvas editor."""

from __future__ import annotations

from tkinter import messagebox

from batikcraft_studio.application import (
    ProjectSessionError,
    StructuredBatificationProjectSession,
)
from batikcraft_studio.i18n import tr
from batikcraft_studio.ui.object_colors import declared_object_colors

from .clipboard_batik_editor import ClipboardBatikEditorWorkspaceView
from .structured_batification_dialog import StructuredBatificationDialog


class StructuredBatificationEditorWorkspaceView(ClipboardBatikEditorWorkspaceView):
    """Expose source-preserving object/group Batification workflows."""

    def batify_selected_object(self) -> None:
        request = self._request_dialog("object")
        if request is None:
            return
        try:
            generation = self._batification_session.batify_object(request=request)
            render = self.session.require_project().get_object(generation.render_object_id)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self._refresh_after_batification()
        self.set_status(
            tr(
                "ai.status.rendered",
                name=render.name,
                version=generation.version,
            )
        )

    def batify_selected_group(self) -> None:
        request = self._request_dialog("group")
        if request is None:
            return
        try:
            generations = self._batification_session.batify_active_group(request=request)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self._refresh_after_batification()
        self.set_status(tr("ai.status.group_rendered", count=len(generations)))

    def rerender_selected_component(self) -> None:
        try:
            generation = self._batification_session.rerender_object()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self._refresh_after_batification()
        self.set_status(tr("ai.status.rerendered", version=generation.version))

    def show_selected_source(self) -> None:
        try:
            source = self._batification_session.show_batification_source()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self._refresh_after_batification()
        self.set_status(tr("ai.status.source_shown", name=source.name))

    def show_selected_latest_render(self) -> None:
        try:
            generation = self._batification_session.show_latest_batification()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self._refresh_after_batification()
        self.set_status(tr("ai.status.latest_shown", version=generation.version))

    def reset_selected_batification(self) -> None:
        if not messagebox.askyesno(
            tr("ai.reset.title"),
            tr("ai.reset.confirm"),
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            self._batification_session.reset_batification(remove_generated=True)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self._refresh_after_batification()
        self.set_status(tr("ai.status.reset"))

    def _request_dialog(self, mode: str):
        primary, secondary = self._selected_colors()
        dialog = StructuredBatificationDialog(
            self,
            mode=mode,
            primary_color=primary,
            secondary_color=secondary,
            provider_id=self._batification_session.batification_provider_id,
        )
        return dialog.result

    def _selected_colors(self) -> tuple[str, str]:
        item = self._active_object()
        if item is None:
            return ("#4E2A1E", "#D9A566")
        primary, secondary = declared_object_colors(item)
        if item.asset_ref is not None:
            sampled_primary, sampled_secondary = self._sampled_object_colors(item)
            primary = primary or sampled_primary
            secondary = secondary or sampled_secondary
        return (primary or "#4E2A1E", secondary or "#D9A566")

    def _refresh_after_batification(self) -> None:
        self.refresh_context()
        self.after_idle(lambda: self._sync_palette_from_selection(announce=False))

    @property
    def _batification_session(self) -> StructuredBatificationProjectSession:
        if not isinstance(self.session, StructuredBatificationProjectSession):
            raise RuntimeError(
                "Editor Batification memerlukan StructuredBatificationProjectSession."
            )
        return self.session


__all__ = ["StructuredBatificationEditorWorkspaceView"]
