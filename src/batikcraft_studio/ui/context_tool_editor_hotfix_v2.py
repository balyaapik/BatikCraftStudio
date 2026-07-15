"""Final viewport hotfix layer using immutable project snapshots."""

from __future__ import annotations

from typing import Any

from PIL import Image

from batikcraft_studio.domain import Project
from batikcraft_studio.imaging.safe_viewport_renderer import (
    project_visual_fingerprint,
    visible_screen_tile_coords,
)

from .context_tool_editor_hotfix import ContextToolEditorWorkspaceView as _HotfixEditor


class ContextToolEditorWorkspaceView(_HotfixEditor):
    """Use a Project aggregate clone instead of unsafe ``deepcopy`` calls."""

    def _submit_visible_tiles(
        self,
        project: Any,
        zoom_scale: float,
        generation: int,
    ) -> None:
        if self._render_shutdown:
            return
        if self._render_future is not None and not self._render_future.done():
            self._render_future.cancel()

        project_snapshot = _clone_project_for_render(project)
        assets_snapshot = {key: bytes(value) for key, value in self.session.assets.items()}
        fingerprint = project_visual_fingerprint(project_snapshot, assets_snapshot)
        preview_left = float(self._preview_left)
        preview_top = float(self._preview_top)

        viewport_left = max(0.0, self.canvas.canvasx(0) - preview_left)
        viewport_top = max(0.0, self.canvas.canvasy(0) - preview_top)
        viewport_width = max(1.0, float(self.canvas.winfo_width()))
        viewport_height = max(1.0, float(self.canvas.winfo_height()))
        tile_coords = visible_screen_tile_coords(
            viewport_left,
            viewport_top,
            viewport_width,
            viewport_height,
            project_snapshot.canvas.width,
            project_snapshot.canvas.height,
            zoom_scale,
            overscan=1,
        )
        active_keys = frozenset(tile_coords)
        renderer = self._safe_renderer

        def worker() -> None:
            rendered: list[tuple[int, int, Image.Image]] = []
            for tile_x, tile_y in tile_coords:
                if self._render_shutdown or generation != self._render_generation:
                    return
                image = renderer.render_tile(
                    project_snapshot,
                    assets_snapshot,
                    project_fingerprint=fingerprint,
                    zoom_scale=zoom_scale,
                    tile_x=tile_x,
                    tile_y=tile_y,
                )
                rendered.append((tile_x, tile_y, image))
            if not self._render_shutdown and generation == self._render_generation:
                self._render_results.put(
                    (
                        generation,
                        rendered,
                        zoom_scale,
                        preview_left,
                        preview_top,
                        active_keys,
                    )
                )

        self._render_future = self._render_executor.submit(worker)


def _clone_project_for_render(project: Project) -> Project:
    """Clone the mutable aggregate while reusing immutable layer value objects."""

    return Project(
        metadata=project.metadata,
        canvas=project.canvas,
        layers=project.layers,
        project_id=project.project_id,
        schema_version=project.schema_version,
        active_layer_id=project.active_layer_id,
        active_object_id=project.active_object_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        revision=project.revision,
        saved_revision=project.saved_revision,
    )


__all__ = ["ContextToolEditorWorkspaceView"]
