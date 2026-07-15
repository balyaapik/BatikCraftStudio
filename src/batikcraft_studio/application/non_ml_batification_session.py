"""Application service for two-object, non-ML Batification."""

from __future__ import annotations

from uuid import uuid4

from batikcraft_studio.domain import LayerObject, ObjectBounds, ObjectKind
from batikcraft_studio.imaging.non_ml_batification import (
    NonMLBatificationError,
    NonMLBatificationOptions,
    batify_with_motif,
)
from batikcraft_studio.imaging.structured_batification import (
    BatificationError,
    renderable_source_content,
)

from .hotfix_session_v2 import FinalHotfixProjectSession
from .session import ProjectSessionError


class NonMLBatificationProjectSession(FinalHotfixProjectSession):
    """Transfer one selected motif into another selected object without a model."""

    def batify_selected_with_motif(
        self,
        options: NonMLBatificationOptions | None = None,
    ) -> LayerObject:
        """Use selection order: source first, motif second.

        The user selects the object to transform, then Shift-selects the Batik motif.
        The original source is kept but hidden; the motif object is not modified.
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


__all__ = ["NonMLBatificationProjectSession"]
