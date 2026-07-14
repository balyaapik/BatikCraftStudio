"""Metadata editing commands for reusable Batik asset objects."""

from __future__ import annotations

from batikcraft_studio.domain import LayerObject
from batikcraft_studio.imaging.batik_asset import ASSET_CATEGORIES

from .object_session import ObjectProjectSession
from .session import ProjectSessionError


class EditableObjectProjectSession(ObjectProjectSession):
    """Expose safe object naming and asset-category edits to the inspector."""

    def update_object_metadata(
        self,
        object_id: str,
        *,
        name: str | None = None,
        category: str | None = None,
    ) -> LayerObject:
        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        object_name = item.name if name is None else name.strip()
        if not object_name:
            raise ProjectSessionError("Nama objek tidak boleh kosong.")
        properties = dict(item.properties)
        if category is not None:
            if category not in ASSET_CATEGORIES:
                raise ProjectSessionError(f"Kategori asset tidak didukung: {category!r}.")
            properties["asset_category"] = category
        updated: LayerObject | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_object(
                object_id,
                name=object_name[:120],
                properties=properties,
            )

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Pembaruan metadata objek tidak menghasilkan perubahan.")
        return updated


__all__ = ["EditableObjectProjectSession"]
