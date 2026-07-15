"""Final session hotfix preserving fill order and object identity."""

from __future__ import annotations

from uuid import uuid4

from batikcraft_studio.domain import LayerObject, ObjectBounds, ObjectKind

from .hotfix_session import (
    HotfixProjectSession,
    _ALPHA_THRESHOLD,
    _GAP_CLOSE_PROJECT_PIXELS,
    _SUPERSAMPLE,
    _fill_enclosed_png_complete,
    _normalize_color,
)
from .session import ProjectSessionError


class FinalHotfixProjectSession(HotfixProjectSession):
    """Correct the reusable-fill reorder semantics in the first hotfix layer."""

    def fill_closed_object(self, object_id: str, color: str) -> tuple[LayerObject, ...]:
        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        if item.kind is ObjectKind.SHAPE:
            # Skip HotfixProjectSession's raster branch and use the stable vector path.
            return super().fill_closed_object(object_id, color)
        if item.kind is not ObjectKind.PAINT_STROKE or item.asset_ref is None:
            raise ProjectSessionError(
                "Fill requires a closed vector shape or one closed paint stroke."
            )

        source_content = self._assets.get(item.asset_ref)
        if source_content is None:
            raise ProjectSessionError("The source stroke asset is unavailable.")
        normalized = _normalize_color(color)
        filled_content = _fill_enclosed_png_complete(source_content, normalized)

        layer_id = project.object_layer_id(item.object_id)
        layer = project.get_layer(layer_id)
        source_index = next(
            index for index, candidate in enumerate(layer.objects)
            if candidate.object_id == item.object_id
        )
        existing = next(
            (
                candidate
                for candidate in layer.objects
                if candidate.object_id != item.object_id
                and (
                    candidate.properties.get("source_stroke_id") == item.object_id
                    or candidate.properties.get("fill_source_object_id") == item.object_id
                )
            ),
            None,
        )
        new_asset_ref = f"assets/{uuid4()}.png"
        properties = {
            "source_format": "ENCLOSED_STROKE_FILL_V2",
            "fill_color": normalized,
            "source_stroke_id": item.object_id,
            "fill_source_object_id": item.object_id,
            "alpha_threshold": _ALPHA_THRESHOLD,
            "gap_close_project_pixels": _GAP_CLOSE_PROJECT_PIXELS,
            "supersample": _SUPERSAMPLE,
        }

        if existing is None:
            fill_object = LayerObject(
                name=f"Isi {item.name}"[:120],
                kind=ObjectKind.RASTER,
                asset_ref=new_asset_ref,
                transform=item.transform,
                bounds=ObjectBounds(item.bounds.width, item.bounds.height),
                properties=properties,
            )
            previous_asset_ref: str | None = None
        else:
            fill_object = existing
            previous_asset_ref = existing.asset_ref

        def mutation() -> None:
            self._assets[new_asset_ref] = filled_content
            if existing is None:
                project.add_object(
                    layer_id,
                    fill_object,
                    index=source_index,
                    select=False,
                )
            else:
                project.update_object(
                    existing.object_id,
                    asset_ref=new_asset_ref,
                    transform=item.transform,
                    bounds=item.bounds,
                    properties=properties,
                )
                refreshed_layer = project.get_layer(layer_id)
                existing_index = next(
                    index for index, candidate in enumerate(refreshed_layer.objects)
                    if candidate.object_id == existing.object_id
                )
                refreshed_source_index = next(
                    index for index, candidate in enumerate(refreshed_layer.objects)
                    if candidate.object_id == item.object_id
                )
                desired_index = max(0, refreshed_source_index - 1)
                if existing_index != desired_index:
                    project.reorder_object(existing.object_id, desired_index)
            if previous_asset_ref is not None:
                self._remove_asset_if_unreferenced(previous_asset_ref)

        self._commit_mutation(mutation)
        result_fill = project.get_object(fill_object.object_id)
        self.set_selected_objects([result_fill.object_id, item.object_id])
        return (result_fill, project.get_object(item.object_id))


__all__ = ["FinalHotfixProjectSession"]
