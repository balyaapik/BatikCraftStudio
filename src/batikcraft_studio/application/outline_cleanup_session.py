"""Preview-first application service for cleaning noisy outline objects."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from batikcraft_studio.domain import LayerObject, ObjectBounds, ObjectKind
from batikcraft_studio.imaging.outline_cleanup import (
    OutlineCleanupError,
    OutlineCleanupOptions,
    OutlineCleanupResult,
    clean_outline,
)
from batikcraft_studio.imaging.structured_batification import (
    BatificationError,
    renderable_source_content,
)

from .external_image_session import ExternalImageProjectSession
from .session import ProjectSessionError


@dataclass(frozen=True, slots=True)
class OutlineCleanupPlan:
    """Immutable object snapshot used while the cleanup dialog is open."""

    source_object: LayerObject
    source_content: bytes
    project_revision: int


@dataclass(frozen=True, slots=True)
class OutlineCleanupPreview:
    """Rendered cleanup candidate that has not changed the project."""

    source_object_id: str
    options: OutlineCleanupOptions
    result: OutlineCleanupResult


class OutlineCleanupProjectSession(ExternalImageProjectSession):
    """Clean one selected raster-like object and replace its pixels only after approval."""

    def prepare_outline_cleanup(
        self,
        source_object_id: str | None = None,
    ) -> OutlineCleanupPlan:
        project = self.require_project()
        selected = self.selected_object_ids
        resolved_id = source_object_id
        if resolved_id is None:
            if len(selected) > 1:
                raise ProjectSessionError(
                    "Pilih tepat satu objek gambar sebelum membuka Rapikan Outline."
                )
            if selected:
                resolved_id = selected[0]
            elif project.active_object_id is not None:
                resolved_id = project.active_object_id
        if resolved_id is None:
            raise ProjectSessionError(
                "Pilih satu objek gambar pada canvas sebelum membuka Rapikan Outline."
            )

        source = self._require_unlocked_object(resolved_id)
        if source.kind is ObjectKind.ERASER_STROKE:
            raise ProjectSessionError("Goresan penghapus tidak dapat dirapikan sebagai outline.")
        try:
            source_content = renderable_source_content(source, self._assets)
        except BatificationError as exc:
            raise ProjectSessionError(str(exc)) from exc
        return OutlineCleanupPlan(
            source_object=source,
            source_content=source_content,
            project_revision=project.revision,
        )

    def render_outline_cleanup_preview(
        self,
        plan: OutlineCleanupPlan,
        options: OutlineCleanupOptions | None = None,
    ) -> OutlineCleanupPreview:
        if not isinstance(plan, OutlineCleanupPlan):
            raise ProjectSessionError("Rencana preview Rapikan Outline tidak valid.")
        settings = options or OutlineCleanupOptions()
        try:
            result = clean_outline(plan.source_content, settings)
        except OutlineCleanupError as exc:
            raise ProjectSessionError(str(exc)) from exc
        return OutlineCleanupPreview(
            source_object_id=plan.source_object.object_id,
            options=settings,
            result=result,
        )

    def commit_outline_cleanup_preview(
        self,
        plan: OutlineCleanupPlan,
        preview: OutlineCleanupPreview,
    ) -> LayerObject:
        """Replace the source pixels in place as exactly one Undo transaction."""

        project = self.require_project()
        if preview.source_object_id != plan.source_object.object_id:
            raise ProjectSessionError("Preview outline tidak cocok dengan objek sumber.")
        if project.revision != plan.project_revision:
            raise ProjectSessionError(
                "Project berubah setelah dialog dibuka. Proses ulang preview sebelum menerapkan."
            )

        source = self._require_unlocked_object(plan.source_object.object_id)
        if source != plan.source_object:
            raise ProjectSessionError(
                "Objek sumber berubah setelah dialog dibuka. Buka ulang Rapikan Outline."
            )

        result = preview.result
        asset_ref = f"assets/{uuid4()}.png"
        original_ref = source.properties.get("outline_cleanup_original_asset_ref")
        if not isinstance(original_ref, str):
            original_ref = source.asset_ref
        properties = dict(source.properties)
        properties.update(
            {
                "source_format": "OUTLINE_CLEANUP_V1",
                "source_asset_ref": asset_ref,
                "outline_cleanup_original_asset_ref": original_ref,
                "outline_cleanup_settings": preview.options.to_properties(),
                "outline_cleanup_removed_components": result.removed_components,
                "outline_cleanup_removed_pixels": result.removed_pixels,
                "outline_cleanup_input_coverage": round(result.input_coverage, 6),
                "outline_cleanup_output_coverage": round(result.output_coverage, 6),
                "outline_cleanup_source_mode": result.resolved_source_mode,
                "outline_cleanup_preview_approved": True,
                "outline_cleanup_replace_in_place": True,
                "humanized": False,
            }
        )
        updated: LayerObject | None = None

        def mutation() -> None:
            nonlocal updated
            self._assets[asset_ref] = result.content
            updated = project.update_object(
                source.object_id,
                kind=ObjectKind.RASTER,
                asset_ref=asset_ref,
                visible=True,
                bounds=ObjectBounds(result.width, result.height),
                properties=properties,
            )

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Hasil outline bersih tidak dapat diterapkan.")
        self.set_selected_objects([source.object_id])
        return project.get_object(source.object_id)


__all__ = [
    "OutlineCleanupPlan",
    "OutlineCleanupPreview",
    "OutlineCleanupProjectSession",
]
