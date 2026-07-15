"""Application service for deterministic Batification and preview-first replacement."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from batikcraft_studio.domain import LayerObject, ObjectBounds, ObjectKind
from batikcraft_studio.imaging.non_ml_batification import (
    NonMLBatificationError,
    NonMLBatificationOptions,
    NonMLBatificationResult,
    batify_with_motif,
)
from batikcraft_studio.imaging.structured_batification import (
    BatificationError,
    renderable_source_content,
)

from .hotfix_session_v2 import FinalHotfixProjectSession
from .session import ProjectSessionError


@dataclass(frozen=True, slots=True)
class NonMLBatificationPlan:
    """Immutable source snapshot used while a modal preview dialog is open."""

    source_object: LayerObject
    source_content: bytes
    project_revision: int


@dataclass(frozen=True, slots=True)
class NonMLBatificationPreview:
    """A rendered candidate that has not yet changed the active project."""

    source_object_id: str
    motif_name: str
    motif_library_key: str | None
    options: NonMLBatificationOptions
    result: NonMLBatificationResult


class NonMLBatificationProjectSession(FinalHotfixProjectSession):
    """Transfer a selected or library motif into an object without a trained model."""

    def prepare_non_ml_batification(
        self,
        source_object_id: str | None = None,
    ) -> NonMLBatificationPlan:
        """Capture one source object without adding an Undo entry or mutating the project."""

        project = self.require_project()
        selected = self.selected_object_ids
        resolved_id = source_object_id
        if resolved_id is None:
            if selected:
                resolved_id = selected[0]
            elif project.active_object_id is not None:
                resolved_id = project.active_object_id
        if resolved_id is None:
            raise ProjectSessionError(
                "Pilih satu objek gambar pada canvas sebelum membuka Batifikasi Non-AI."
            )

        source = self._require_unlocked_object(resolved_id)
        if source.kind is ObjectKind.ERASER_STROKE:
            raise ProjectSessionError("Goresan penghapus tidak dapat dibatifikasi.")
        try:
            source_content = renderable_source_content(source, self._assets)
        except BatificationError as exc:
            raise ProjectSessionError(str(exc)) from exc
        return NonMLBatificationPlan(
            source_object=source,
            source_content=source_content,
            project_revision=project.revision,
        )

    def render_non_ml_batification_preview(
        self,
        plan: NonMLBatificationPlan,
        motif_content: bytes,
        *,
        motif_name: str,
        motif_library_key: str | None = None,
        options: NonMLBatificationOptions | None = None,
    ) -> NonMLBatificationPreview:
        """Render a candidate entirely in memory; the project remains untouched."""

        if not isinstance(plan, NonMLBatificationPlan):
            raise ProjectSessionError("Rencana preview Batifikasi Non-AI tidak valid.")
        settings = options or NonMLBatificationOptions()
        try:
            result = batify_with_motif(plan.source_content, motif_content, settings)
        except NonMLBatificationError as exc:
            raise ProjectSessionError(str(exc)) from exc
        return NonMLBatificationPreview(
            source_object_id=plan.source_object.object_id,
            motif_name=(motif_name.strip() or "Motif Batik")[:160],
            motif_library_key=motif_library_key,
            options=settings,
            result=result,
        )

    def commit_non_ml_batification_preview(
        self,
        plan: NonMLBatificationPlan,
        preview: NonMLBatificationPreview,
    ) -> LayerObject:
        """Replace the source object's pixels in place as exactly one Undo transaction."""

        project = self.require_project()
        if preview.source_object_id != plan.source_object.object_id:
            raise ProjectSessionError("Preview tidak cocok dengan objek sumber yang dipilih.")
        if project.revision != plan.project_revision:
            raise ProjectSessionError(
                "Project berubah setelah dialog dibuka. Proses ulang preview sebelum menekan OK."
            )

        source = self._require_unlocked_object(plan.source_object.object_id)
        if source != plan.source_object:
            raise ProjectSessionError(
                "Objek sumber berubah setelah dialog dibuka. Proses ulang Batifikasi."
            )

        result = preview.result
        asset_ref = f"assets/{uuid4()}.png"
        original_ref = source.properties.get("batification_original_asset_ref")
        if not isinstance(original_ref, str):
            original_ref = source.asset_ref
        properties = dict(source.properties)
        properties.update(
            {
                "source_format": "NON_ML_BATIFICATION_V2",
                "source_asset_ref": asset_ref,
                "batification_original_asset_ref": original_ref,
                "batification_provider": "local-motif-transfer-v2",
                "batification_source_object_id": source.object_id,
                "batification_motif_name": preview.motif_name,
                "batification_motif_library_key": preview.motif_library_key,
                "batification_settings": preview.options.to_properties(),
                "batification_palette": list(result.palette),
                "batification_darkest_color": result.darkest_color,
                "batification_line_like_source": result.line_like_source,
                "batification_mask_coverage": round(result.mask_coverage, 6),
                "batification_preview_approved": True,
                "batification_replace_in_place": True,
                "batification_editable_component": True,
                "humanized": False,
            }
        )
        updated: LayerObject | None = None

        def mutation() -> None:
            nonlocal updated
            self._assets[asset_ref] = result.content
            updated = project.update_object(
                source.object_id,
                name=f"Batifikasi {source.name}"[:120],
                kind=ObjectKind.RASTER,
                asset_ref=asset_ref,
                visible=True,
                bounds=ObjectBounds(result.width, result.height),
                properties=properties,
            )

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Hasil Batifikasi tidak dapat diterapkan ke objek.")
        self.set_selected_objects([source.object_id])
        return project.get_object(source.object_id)

    def batify_selected_with_motif(
        self,
        options: NonMLBatificationOptions | None = None,
    ) -> LayerObject:
        """Use selection order: source first, motif second.

        This legacy direct command remains available for compatibility. The preview
        dialog uses ``prepare_*``, ``render_*``, and ``commit_*`` instead.
        """

        selected = self.selected_object_ids
        if len(selected) != 2:
            raise ProjectSessionError(
                "Pilih tepat dua objek: objek sumber terlebih dahulu, lalu Shift-pilih motif batik."
            )
        return self.batify_object_with_motif(selected[0], selected[1], options=options)

    def batify_object_with_motif(
        self,
        source_object_id: str,
        motif_object_id: str,
        *,
        options: NonMLBatificationOptions | None = None,
    ) -> LayerObject:
        """Create a non-destructive Batik render in the source object's layer."""

        if source_object_id == motif_object_id:
            raise ProjectSessionError("Objek sumber dan motif batik harus berbeda.")
        project = self.require_project()
        source = self._require_unlocked_object(source_object_id)
        motif = project.get_object(motif_object_id)
        if motif.kind is ObjectKind.ERASER_STROKE:
            raise ProjectSessionError("Goresan penghapus tidak dapat digunakan sebagai motif batik.")

        try:
            source_content = renderable_source_content(source, self._assets)
            motif_content = renderable_source_content(motif, self._assets)
            settings = options or NonMLBatificationOptions()
            result = batify_with_motif(source_content, motif_content, settings)
        except (BatificationError, NonMLBatificationError) as exc:
            raise ProjectSessionError(str(exc)) from exc

        source_layer_id = project.object_layer_id(source.object_id)
        source_layer = project.get_layer(source_layer_id)
        source_index = next(
            index
            for index, candidate in enumerate(source_layer.objects)
            if candidate.object_id == source.object_id
        )
        asset_ref = f"assets/{uuid4()}.png"
        properties = {
            "source_format": "NON_ML_BATIFICATION_V1",
            "batification_provider": "local-motif-transfer-v1",
            "batification_source_object_id": source.object_id,
            "batification_motif_object_id": motif.object_id,
            "batification_settings": settings.to_properties(),
            "batification_palette": list(result.palette),
            "batification_darkest_color": result.darkest_color,
            "batification_line_like_source": result.line_like_source,
            "batification_mask_coverage": round(result.mask_coverage, 6),
            "batification_non_destructive": True,
            "batification_editable_component": True,
        }
        output = LayerObject(
            name=f"Batifikasi {source.name}"[:120],
            kind=ObjectKind.MOTIF,
            asset_ref=asset_ref,
            visible=True,
            locked=False,
            opacity=source.opacity,
            transform=source.transform,
            bounds=ObjectBounds(result.width, result.height),
            properties=properties,
        )

        def mutation() -> None:
            self._assets[asset_ref] = result.content
            project.update_object(source.object_id, visible=False)
            project.add_object(
                source_layer_id,
                output,
                index=source_index + 1,
                select=True,
            )

        self._commit_mutation(mutation)
        self.set_selected_objects([output.object_id])
        return project.get_object(output.object_id)


__all__ = [
    "NonMLBatificationPlan",
    "NonMLBatificationPreview",
    "NonMLBatificationProjectSession",
]
