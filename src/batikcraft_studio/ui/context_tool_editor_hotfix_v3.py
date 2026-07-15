"""Viewport hotfix that separates project background from transparent artwork tiles."""

from __future__ import annotations

from typing import Any

from batikcraft_studio.imaging.artwork_viewport_renderer import ArtworkViewportRenderer

from .context_tool_editor_hotfix_v2 import ContextToolEditorWorkspaceView as _HotfixV2Editor


class ContextToolEditorWorkspaceView(_HotfixV2Editor):
    """Prevent brush refreshes from appearing as opaque tile-sized color blocks."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._project_background_id: int | None = None
        super().__init__(*args, **kwargs)
        previous_renderer = self._safe_renderer
        self._safe_renderer = ArtworkViewportRenderer()
        self._cached_renderer = self._safe_renderer
        previous_renderer.clear_project()
        self._increment_render_generation()
        self._schedule_render()

    def _kick_tile_render(
        self,
        project: Any,
        zoom_scale: float,
        generation: int,
        content_width: float,
        content_height: float,
    ) -> None:
        self._draw_project_background(project, zoom_scale)
        super()._kick_tile_render(
            project,
            zoom_scale,
            generation,
            content_width,
            content_height,
        )

    def _draw_project_background(self, project: Any, zoom_scale: float) -> None:
        left = float(self._preview_left)
        top = float(self._preview_top)
        right = left + float(project.canvas.width) * zoom_scale
        bottom = top + float(project.canvas.height) * zoom_scale
        background = str(project.canvas.background_color)

        background_id = self._project_background_id
        if background_id is None:
            background_id = self.canvas.create_rectangle(
                left,
                top,
                right,
                bottom,
                fill=background,
                outline="",
                tags=("project-background", "canvas-chrome"),
            )
            self._project_background_id = background_id
        else:
            self.canvas.coords(background_id, left, top, right, bottom)
            self.canvas.itemconfigure(background_id, fill=background)

        # The shadow is created immediately before this method by the base renderer.
        # Artwork tiles are created afterwards, but existing tiles may still be present.
        tile_ids = self.canvas.find_withtag("project-tile")
        if tile_ids:
            self.canvas.tag_lower(background_id, tile_ids[0])

    def _clear_tile_overlays(self) -> None:
        background_id = self._project_background_id
        if background_id is not None:
            self.canvas.delete(background_id)
            self._project_background_id = None
        super()._clear_tile_overlays()


__all__ = ["ContextToolEditorWorkspaceView"]
