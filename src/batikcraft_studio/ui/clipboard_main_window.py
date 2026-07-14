"""Main-window commands for copying and pasting selected canvas objects."""

from __future__ import annotations

from .main_window import MainWindow


class ClipboardMainWindow(MainWindow):
    """Expose object clipboard actions to menus and global shortcuts."""

    def editor_copy(self) -> None:
        self._editor().copy_active_object()

    def editor_paste(self) -> None:
        self._editor().paste_object()


__all__ = ["ClipboardMainWindow"]
