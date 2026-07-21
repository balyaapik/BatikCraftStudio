"""Canvas object clipboard UI and conflict-free drawing shortcuts."""

from __future__ import annotations

import logging

from collections.abc import Callable

from batikcraft_studio.application import ClipboardProjectSession, ProjectSessionError
from batikcraft_studio.i18n import tr

from .keyboard import (
    ISEN_TOOL_SEQUENCE,
    SELECT_TOOL_SEQUENCE,
    run_single_key_shortcut,
)
from .polished_batik_editor import PolishedBatikEditorWorkspaceView


class ClipboardBatikEditorWorkspaceView(PolishedBatikEditorWorkspaceView):
    """Expose copy/paste for selected canvas objects."""

    def copy_active_object(self) -> None:
        try:
            item = self._clipboard_session.copy_object()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - kegagalan tak terduga harus terlihat
            logging.getLogger(__name__).exception("Salin objek gagal")
            self.set_status(f"Salin objek gagal: {type(exc).__name__}: {exc}")
            return
        self.set_status(tr("clipboard.copied", name=item.name))

    def paste_object(self) -> None:
        try:
            item = self._clipboard_session.paste_object()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - kegagalan tak terduga harus terlihat
            logging.getLogger(__name__).exception("Tempel objek gagal")
            self.set_status(f"Tempel objek gagal: {type(exc).__name__}: {exc}")
            return
        self.refresh_context()
        self.after_idle(lambda: self._sync_palette_from_selection(announce=False))
        self.set_status(tr("clipboard.pasted", name=item.name))

    def _bind_compact_shortcuts(self) -> None:
        bindings: tuple[tuple[str, Callable[[], object]], ...] = (
            (SELECT_TOOL_SEQUENCE, self.activate_select_tool),
            ("<Key-b>", self.open_brush_settings),
            ("<Key-e>", self.open_eraser_settings),
            ("<Key-l>", lambda: self.open_shape_settings("line")),
            ("<Key-r>", lambda: self.open_shape_settings("rectangle")),
            ("<Key-o>", lambda: self.open_shape_settings("ellipse")),
            ("<Key-p>", lambda: self.open_shape_settings("polygon")),
            ("<Key-m>", self.open_motif_settings),
            (ISEN_TOOL_SEQUENCE, self.open_isen_settings),
        )
        for sequence, command in bindings:
            self.bind_all(
                sequence,
                lambda event, action=command: run_single_key_shortcut(event, action),
            )

    @property
    def _clipboard_session(self) -> ClipboardProjectSession:
        if not isinstance(self.session, ClipboardProjectSession):
            raise RuntimeError("Editor memerlukan ClipboardProjectSession.")
        return self.session


__all__ = ["ClipboardBatikEditorWorkspaceView"]
