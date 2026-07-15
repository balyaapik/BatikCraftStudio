"""Application service for inserting normalized external images as editable objects."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from batikcraft_studio.domain import LayerObject, ObjectBounds, ObjectKind, Transform
from batikcraft_studio.imaging.raster import RasterImageError, normalize_raster_image

from .pretrained_ai_batification_session import PretrainedAIBatificationProjectSession
from .session import ProjectSessionError


class ExternalImageProjectSession(PretrainedAIBatificationProjectSession):
    """Insert TIFF/JPEG/PNG/WebP and other Pillow-readable images into the canvas."""

    def import_external_image(
        self,
        filename: str,
        content: bytes | bytearray | memoryview,
        *,
        position: tuple[float, float] | None = None,
        target_layer_id: str | None = None,
        library_key: str | None = None,
        category: str = "ornamen",
    ) -> LayerObject:
        """Create one transformable raster object and keep the operation undoable."""

        try:
            raster = normalize_raster_image(content)
        except RasterImageError as exc:
            raise ProjectSessionError(str(exc)) from exc

        project = self.require_project()
        target, add_target = self._resolve_object_layer(
            target_layer_id,
            name="Gambar Impor",
        )
        if position is None:
            center_x = project.canvas.width / 2
            center_y = project.canvas.height / 2
        else:
            center_x = min(max(float(position[0]), 0.0), float(project.canvas.width))
            center_y = min(max(float(position[1]), 0.0), float(project.canvas.height))

        scale = min(
            1.0,
            project.canvas.width * 0.65 / raster.width,
            project.canvas.height * 0.65 / raster.height,
        )
        original_name = Path(filename).name or "gambar-impor.png"
        stem = Path(original_name).stem.strip() or "Gambar Impor"
        asset_ref = f"assets/{uuid4()}.png"
        properties: dict[str, object] = {
            "source_format": raster.source_format,
            "original_name": original_name,
            "source_asset_ref": asset_ref,
            "asset_category": category,
            "humanized": False,
            "external_image_import": True,
            "transformable": True,
        }
        if library_key:
            properties["personal_library_key"] = library_key

        item = LayerObject(
            name=stem[:120],
            kind=ObjectKind.RASTER,
            asset_ref=asset_ref,
            transform=Transform(
                x=center_x,
                y=center_y,
                scale_x=scale,
                scale_y=scale,
            ),
            bounds=ObjectBounds(raster.width, raster.height),
            properties=properties,
        )

        def mutation() -> None:
            if add_target:
                project.add_layer(target, select=False)
            self._assets[asset_ref] = raster.content
            project.add_object(target.layer_id, item, select=True)

        self._commit_mutation(mutation)
        self.set_selected_objects([item.object_id])
        return project.get_object(item.object_id)


__all__ = ["ExternalImageProjectSession"]
