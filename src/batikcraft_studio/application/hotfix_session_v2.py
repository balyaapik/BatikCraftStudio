"""Final session hotfix preserving fill order and object identity."""

from __future__ import annotations

from uuid import uuid4

from batikcraft_studio.domain import LayerObject, ObjectBounds, ObjectKind

from . import hotfix_session as hotfix
from .session import ProjectSessionError


class FinalHotfixProjectSession(hotfix.HotfixProjectSession):
    """Correct the reusable-fill reorder semantics in the first hotfix layer."""

    def fill_closed_object(self, object_id: str, color: str) -> tuple[LayerObject, ...]:
        """Fill bidang tertutup dan satukan hasilnya ke objek goresan itu sendiri.

        Tidak ada objek "Isi" terpisah: interior diisi warna lalu dikomposit di
        bawah goresan asli, dan asset objek yang sama diganti. Mask interior
        selalu dihitung dari goresan asli (``source_stroke_ref``) sehingga fill
        ulang dengan warna lain tetap berfungsi.
        """

        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        if item.kind is ObjectKind.SHAPE:
            return super().fill_closed_object(object_id, color)
        if item.kind is not ObjectKind.PAINT_STROKE or item.asset_ref is None:
            raise ProjectSessionError(
                "Fill requires a closed vector shape or one closed paint stroke."
            )

        stroke_ref = str(item.properties.get("source_stroke_ref") or item.asset_ref)
        stroke_content = self._assets.get(stroke_ref)
        if stroke_content is None:
            stroke_ref = item.asset_ref
            stroke_content = self._assets.get(stroke_ref)
        if stroke_content is None:
            raise ProjectSessionError("The source stroke asset is unavailable.")

        normalized = hotfix._normalize_color(color)
        combined_content = hotfix._fill_enclosed_png_unified(stroke_content, normalized)
        new_asset_ref = f"assets/{uuid4()}.png"
        properties = dict(item.properties)
        properties.update(
            {
                "source_format": "ENCLOSED_STROKE_FILL_UNIFIED",
                "fill_color": normalized,
                "source_stroke_ref": stroke_ref,
                "alpha_threshold": hotfix._ALPHA_THRESHOLD,
                "gap_close_project_pixels": hotfix._GAP_CLOSE_PROJECT_PIXELS,
                "supersample": hotfix._SUPERSAMPLE,
            }
        )

        layer_id = project.object_layer_id(item.object_id)
        legacy_fills = tuple(
            candidate
            for candidate in project.get_layer(layer_id).objects
            if candidate.object_id != item.object_id
            and (
                candidate.properties.get("source_stroke_id") == item.object_id
                or candidate.properties.get("fill_source_object_id") == item.object_id
            )
        )

        def mutation() -> None:
            self._assets[new_asset_ref] = combined_content
            for candidate in legacy_fills:
                project.remove_object(candidate.object_id)
            project.update_object(
                item.object_id,
                asset_ref=new_asset_ref,
                properties=properties,
            )

        self._commit_mutation(mutation)
        self.set_selected_objects([item.object_id])
        return (project.get_object(item.object_id),)


__all__ = ["FinalHotfixProjectSession"]
