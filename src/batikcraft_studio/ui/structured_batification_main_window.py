"""Main-window bridge for Structured Batification menu commands."""

from __future__ import annotations

from .clipboard_main_window import ClipboardMainWindow


class StructuredBatificationMainWindow(ClipboardMainWindow):
    """Expose Structured Batification commands to the application menu."""

    def batify_selected_object(self) -> None:
        self._editor().batify_selected_object()

    def batify_selected_group(self) -> None:
        self._editor().batify_selected_group()

    def rerender_selected_component(self) -> None:
        self._editor().rerender_selected_component()

    def show_selected_source(self) -> None:
        self._editor().show_selected_source()

    def show_selected_latest_render(self) -> None:
        self._editor().show_selected_latest_render()

    def reset_selected_batification(self) -> None:
        self._editor().reset_selected_batification()


__all__ = ["StructuredBatificationMainWindow"]
