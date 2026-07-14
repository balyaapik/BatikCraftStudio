"""Main-window bridge for Batik process planning."""

from __future__ import annotations

from .multi_object_main_window import MultiObjectMainWindow


class BatikProcessMainWindow(MultiObjectMainWindow):
    """Expose the process studio to the application shell."""

    def open_batik_process_studio(self) -> None:
        self._editor().open_batik_process_studio()


__all__ = ["BatikProcessMainWindow"]
