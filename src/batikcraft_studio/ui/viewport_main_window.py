"""Main-window bridge for viewport and standard edit commands."""

from __future__ import annotations

from .process_main_window import BatikProcessMainWindow


class ViewportMainWindow(BatikProcessMainWindow):
    """Expose zoom, grid, ruler, and Cut commands to the application shell."""

    def editor_cut(self) -> None:
        self._editor().cut_selected_objects()

    def zoom_in(self) -> None:
        self._editor().zoom_in()

    def zoom_out(self) -> None:
        self._editor().zoom_out()

    def zoom_fit(self) -> None:
        self._editor().zoom_fit()

    def zoom_actual_size(self) -> None:
        self._editor().zoom_actual_size()

    def set_grid_visible(self, visible: bool) -> None:
        self._editor().set_grid_visible(visible)

    def set_ruler_visible(self, visible: bool) -> None:
        self._editor().set_ruler_visible(visible)

    @property
    def grid_visible(self) -> bool:
        return bool(self._editor().grid_visible)

    @property
    def ruler_visible(self) -> bool:
        return bool(self._editor().ruler_visible)


__all__ = ["ViewportMainWindow"]
