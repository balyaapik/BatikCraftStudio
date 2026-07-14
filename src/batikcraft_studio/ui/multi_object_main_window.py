"""Main-window bridge for multi-object group commands."""

from __future__ import annotations

from .offline_ai_main_window import OfflineAIMainWindow


class MultiObjectMainWindow(OfflineAIMainWindow):
    """Expose grouping and ungrouping to the application menu."""

    def group_selected_objects(self) -> None:
        self._editor().group_selected_objects()

    def ungroup_selected_objects(self) -> None:
        self._editor().ungroup_selected_objects()


__all__ = ["MultiObjectMainWindow"]
