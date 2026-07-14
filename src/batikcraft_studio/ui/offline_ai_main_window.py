"""Main-window bridge for offline dataset, model, and selection commands."""

from __future__ import annotations

from .structured_batification_main_window import StructuredBatificationMainWindow


class OfflineAIMainWindow(StructuredBatificationMainWindow):
    """Expose Milestone 4B commands to the application menu."""

    def open_dataset_studio(self) -> None:
        self._editor().open_dataset_studio()

    def open_offline_model_manager(self) -> None:
        self._editor().open_offline_model_manager()

    def begin_ai_rectangle_selection(self) -> None:
        self._editor().begin_ai_rectangle_selection()


__all__ = ["OfflineAIMainWindow"]
