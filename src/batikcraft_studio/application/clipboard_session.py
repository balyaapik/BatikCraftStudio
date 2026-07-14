"""Internal object clipboard with undoable paste support."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from uuid import uuid4

from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    Transform,
)

from .interactive_transform_session import InteractiveTransformProjectSession
from .session import LayerLockedError, ProjectSessionError


@dataclass(frozen=True, slots=True)
class ObjectClipboardSnapshot:
    """One copied object plus every embedded asset it references."""

    item: LayerObject
    source_layer_id: str
    assets: tuple[tuple[str, bytes], ...]

    @property
    def asset_map(self) -> MappingProxyType[str, bytes]:
        return MappingProxyType(dict(self.assets))


class ClipboardProjectSession(InteractiveTransformProjectSession):
    """Add copy/paste semantics without using the operating-system text clipboard."""

    def __init__(self) -> None:
        super().__init__()
        self._object_clipboard: ObjectClipboardSnapshot | None = None
        self._clipboard_paste_count = 0

    @property
    def has_object_clipboard(self) -> bool:
        return self._object_clipboard is not None

    @property
    def object_clipboard(self) -> ObjectClipboardSnapshot | None:
        return self._object_clipboard

    def copy_object(self, object_id: str | None = None) -> LayerObject:
        """Copy an object snapshot without mutating project history."""

        project = self.require_project()
        selected_id = object_id or project.active_object_id
        if selected_id is None:
            raise ProjectSessionError("Pilih satu objek pada canvas sebelum menyalin.")
        item = project.get_object(selected_id)
        source_layer_id = project.object_layer_id(selected_id)
        references = _referenced_asset_paths(item)
        assets = tuple(
            sorted(
                (asset_ref, bytes(self._assets[asset_ref]))
                for asset_ref in references
                if asset_ref in self._assets
            )
        )
        self._object_clipboard = ObjectClipboardSnapshot(
            item=item,
            source_layer_id=source_layer_id,
            assets=assets,
        )
        self._clipboard_paste_count = 0
        return item

    def paste_object(
        self,
        *,
        target_layer_id: str | None = None,
        offset: tuple[float, float] = (24.0, 24.0),
    ) -> LayerObject:
        """Paste the copied object into an editable layer as one Undo step."""

        project = self.require_project()
        clipboard = self._object_clipboard
        if clipboard is None:
            raise ProjectSessionError("Clipboard objek masih kosong.")

        target, add_target = self._resolve_paste_target(
            target_layer_id,
            source_layer_id=clipboard.source_layer_id,
        )
        paste_number = self._clipboard_paste_count + 1
        delta_x = float(offset[0]) * paste_number
        delta_y = float(offset[1]) * paste_number
        source = clipboard.item
        remapped_assets = {
            old_ref: f"assets/{uuid4()}.png" for old_ref, _content in clipboard.assets
        }
        properties = {
            key: remapped_assets.get(value, value)
            for key, value in source.properties.items()
        }
        pasted = LayerObject(
            name=_copy_name(source.name),
            kind=source.kind,
            asset_ref=(
                remapped_assets.get(source.asset_ref, source.asset_ref)
                if source.asset_ref is not None
                else None
            ),
            visible=source.visible,
            locked=False,
            opacity=source.opacity,
            transform=Transform(
                x=source.transform.x + delta_x,
                y=source.transform.y + delta_y,
                rotation_degrees=source.transform.rotation_degrees,
                scale_x=source.transform.scale_x,
                scale_y=source.transform.scale_y,
            ),
            bounds=source.bounds,
            properties=properties,
        )

        def mutation() -> None:
            if add_target:
                project.add_layer(target, select=False)
            for old_ref, content in clipboard.assets:
                self._assets[remapped_assets[old_ref]] = bytes(content)
            project.add_object(target.layer_id, pasted, select=True)

        self._commit_mutation(mutation)
        self._clipboard_paste_count = paste_number
        return pasted

    def _resolve_paste_target(
        self,
        target_layer_id: str | None,
        *,
        source_layer_id: str,
    ) -> tuple[Layer, bool]:
        project = self.require_project()
        candidate_ids: list[str] = []
        if target_layer_id is not None:
            candidate_ids.append(target_layer_id)
        if project.active_object_id is not None:
            candidate_ids.append(project.object_layer_id(project.active_object_id))
        if project.active_layer_id is not None:
            candidate_ids.append(project.active_layer_id)
        if any(layer.layer_id == source_layer_id for layer in project.layers):
            candidate_ids.append(source_layer_id)

        parent_id: str | None = None
        seen: set[str] = set()
        for layer_id in candidate_ids:
            if layer_id in seen:
                continue
            seen.add(layer_id)
            layer = project.get_layer(layer_id)
            if layer.node_kind is LayerNodeKind.GROUP:
                parent_id = layer.layer_id
                continue
            if project.is_layer_effectively_locked(layer.layer_id):
                if target_layer_id == layer.layer_id:
                    raise LayerLockedError(f"Lapis {layer.name!r} sedang dikunci.")
                parent_id = layer.parent_id
                continue
            if layer.asset_ref is None:
                return layer, False
            parent_id = layer.parent_id

        return (
            Layer(
                name="Objek Tempel",
                kind=LayerKind.BATIKIFIED_OBJECT,
                node_kind=LayerNodeKind.LAYER,
                parent_id=parent_id,
                properties={
                    "object_container": True,
                    "object_role": "clipboard",
                },
            ),
            True,
        )


def _referenced_asset_paths(item: LayerObject) -> set[str]:
    references: set[str] = set()
    if item.asset_ref is not None:
        references.add(item.asset_ref)
    for value in item.properties.values():
        if isinstance(value, str) and value.startswith("assets/"):
            references.add(value)
    return references


def _copy_name(name: str) -> str:
    suffix = " salinan"
    maximum = max(1, 120 - len(suffix))
    return f"{name[:maximum].rstrip()}{suffix}"


__all__ = [
    "ClipboardProjectSession",
    "ObjectClipboardSnapshot",
]
