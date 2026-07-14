"""Batch clipboard actions used by the zoomable canvas context menu."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from batikcraft_studio.domain import Layer, LayerObject, Transform

from .canvas_structure_session import CanvasStructureProjectSession
from .clipboard_session import ObjectClipboardSnapshot
from .session import ProjectSessionError

_GROUP_KEYS = {"object_group_id", "object_group_name"}


@dataclass(frozen=True, slots=True)
class MultiObjectClipboardSnapshot:
    """A stable copy of one or more selected objects and their embedded assets."""

    items: tuple[ObjectClipboardSnapshot, ...]

    @property
    def object_count(self) -> int:
        return len(self.items)


class ViewportProjectSession(CanvasStructureProjectSession):
    """Add batch Cut/Copy/Paste/Delete without changing the project schema."""

    def __init__(self, model_root: Path | str | None = None) -> None:
        super().__init__(model_root)
        self._multi_object_clipboard: MultiObjectClipboardSnapshot | None = None
        self._multi_clipboard_paste_count = 0

    @property
    def multi_object_clipboard(self) -> MultiObjectClipboardSnapshot | None:
        return self._multi_object_clipboard

    @property
    def has_multi_object_clipboard(self) -> bool:
        return self._multi_object_clipboard is not None

    def copy_selected_objects(self) -> tuple[LayerObject, ...]:
        """Copy the current multi-selection without adding an Undo entry."""

        project = self.require_project()
        selected = self.selected_objects
        if not selected and project.active_object_id is not None:
            selected = (project.get_object(project.active_object_id),)
        if not selected:
            raise ProjectSessionError("Pilih minimal satu objek sebelum menyalin.")

        snapshots: list[ObjectClipboardSnapshot] = []
        for item in selected:
            references = _referenced_asset_paths(item)
            assets = tuple(
                sorted(
                    (asset_ref, bytes(self._assets[asset_ref]))
                    for asset_ref in references
                    if asset_ref in self._assets
                )
            )
            snapshots.append(
                ObjectClipboardSnapshot(
                    item=item,
                    source_layer_id=project.object_layer_id(item.object_id),
                    assets=assets,
                )
            )
        self._multi_object_clipboard = MultiObjectClipboardSnapshot(tuple(snapshots))
        self._multi_clipboard_paste_count = 0
        return selected

    def cut_selected_objects(self) -> tuple[LayerObject, ...]:
        """Copy and remove the current selection as one Undoable deletion."""

        copied = self.copy_selected_objects()
        self.delete_selected_objects()
        return copied

    def paste_selected_objects(
        self,
        *,
        target_layer_id: str | None = None,
        offset: tuple[float, float] = (24.0, 24.0),
    ) -> tuple[LayerObject, ...]:
        """Paste all copied objects while preserving relative grouping."""

        clipboard = self._multi_object_clipboard
        if clipboard is None:
            if self.has_object_clipboard:
                pasted = self.paste_object(target_layer_id=target_layer_id, offset=offset)
                self.set_selected_objects([pasted.object_id])
                return (pasted,)
            raise ProjectSessionError("Clipboard objek masih kosong.")

        project = self.require_project()
        paste_number = self._multi_clipboard_paste_count + 1
        delta_x = float(offset[0]) * paste_number
        delta_y = float(offset[1]) * paste_number
        group_map: dict[str, str] = {}
        targets: dict[str, tuple[Layer, bool]] = {}
        additions: list[tuple[Layer, bool, LayerObject, dict[str, bytes]]] = []

        for snapshot in clipboard.items:
            source = snapshot.item
            source_group = source.properties.get("object_group_id")
            if isinstance(source_group, str) and source_group:
                group_map.setdefault(source_group, str(uuid4()))

        for snapshot in clipboard.items:
            source = snapshot.item
            target_key = target_layer_id or snapshot.source_layer_id
            if target_key not in targets:
                targets[target_key] = self._resolve_paste_target(
                    target_layer_id,
                    source_layer_id=snapshot.source_layer_id,
                )
            target, add_target = targets[target_key]
            remapped_assets = {
                old_ref: f"assets/{uuid4()}.png"
                for old_ref, _content in snapshot.assets
            }
            properties = {
                key: remapped_assets.get(value, value)
                for key, value in source.properties.items()
                if key not in _GROUP_KEYS
            }
            source_group = source.properties.get("object_group_id")
            if isinstance(source_group, str) and source_group in group_map:
                properties["object_group_id"] = group_map[source_group]
                properties["object_group_name"] = source.properties.get(
                    "object_group_name",
                    "Grup Objek",
                )
            item = LayerObject(
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
            asset_bytes = {
                remapped_assets[old_ref]: bytes(content)
                for old_ref, content in snapshot.assets
            }
            additions.append((target, add_target, item, asset_bytes))

        def mutation() -> None:
            added_layers: set[str] = set()
            for target, add_target, item, asset_bytes in additions:
                if add_target and target.layer_id not in added_layers:
                    project.add_layer(target, select=False)
                    added_layers.add(target.layer_id)
                self._assets.update(asset_bytes)
                project.add_object(target.layer_id, item, select=False)

        self._commit_mutation(mutation)
        pasted = tuple(item for _target, _add, item, _assets in additions)
        self._multi_clipboard_paste_count = paste_number
        self.set_selected_objects([item.object_id for item in pasted])
        return pasted

    def delete_selected_objects(self) -> tuple[LayerObject, ...]:
        """Delete the current multi-selection as one Undo transaction."""

        selected = self.selected_objects
        if not selected:
            project = self.require_project()
            if project.active_object_id is not None:
                selected = (project.get_object(project.active_object_id),)
        if not selected:
            raise ProjectSessionError("Pilih minimal satu objek sebelum menghapus.")
        for item in selected:
            self._require_unlocked_object(item.object_id)
        project = self.require_project()
        removed = tuple(selected)

        def mutation() -> None:
            for item in removed:
                project.remove_object(item.object_id)
            self._remove_unreferenced_assets()

        self._commit_mutation(mutation)
        self.clear_object_selection()
        return removed


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


__all__ = ["MultiObjectClipboardSnapshot", "ViewportProjectSession"]
