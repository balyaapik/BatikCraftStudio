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

_NON_CLONED_PROPERTY_KEYS = {"object_group_id", "object_group_name"}


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
        # Hanya nilai berupa string yang dapat menjadi kunci pemetaan aset.
        # Properti bernilai dict/list (mis. batification_settings dan
        # batification_metadata pada hasil BatikBrew) sebelumnya membuat
        # paste gagal dengan "unhashable type: 'dict'", sehingga hasil AI
        # hanya bisa digandakan lewat panel layer.
        properties = {
            key: _remap_asset_values(value, remapped_assets)
            for key, value in source.properties.items()
            if key not in _NON_CLONED_PROPERTY_KEYS
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
        """Resolve the paste destination using the active layer as the primary target.

        Resolution order
        ----------------
        1. Explicit *target_layer_id* → validate and use directly.
        2. Active layer (``project.active_layer_id``) if it is an unlocked container.
        3. The layer that owns the active object (fallback for object selection).
        4. The original source layer (if still valid and unlocked).
        5. Create a new paste layer as a last resort.

        Locked active layers are rejected with a clear error; they are never silently
        bypassed.
        """
        project = self.require_project()

        # ---- Explicit caller-supplied target ----
        if target_layer_id is not None:
            target = project.get_layer(target_layer_id)
            if target.node_kind is LayerNodeKind.GROUP:
                raise LayerLockedError(
                    "Paste target must be an editable layer, not a folder."
                )
            if project.is_layer_effectively_locked(target.layer_id):
                raise LayerLockedError(f"Lapis {target.name!r} sedang dikunci.")
            if target.asset_ref is None:
                return target, False

        # ---- Active layer (current tree selection) ----
        if project.active_layer_id is not None:
            active = project.get_layer(project.active_layer_id)
            if active.node_kind is LayerNodeKind.LAYER and active.asset_ref is None:
                if project.is_layer_effectively_locked(active.layer_id):
                    raise LayerLockedError(
                        f"Layer {active.name!r} is locked and cannot receive pasted objects. "
                        "Unlock the layer or select a different layer."
                    )
                return active, False
            if active.node_kind is LayerNodeKind.GROUP:
                # Folder selected; find last child or create a new one.
                children = project.children_of(active.layer_id)
                for child in reversed(children):
                    if (
                        child.node_kind is LayerNodeKind.LAYER
                        and child.asset_ref is None
                        and not project.is_layer_effectively_locked(child.layer_id)
                    ):
                        return child, False
                return (
                    Layer(
                        name="Objek Tempel",
                        kind=LayerKind.BATIKIFIED_OBJECT,
                        node_kind=LayerNodeKind.LAYER,
                        parent_id=active.layer_id,
                        properties={"object_container": True, "object_role": "clipboard"},
                    ),
                    True,
                )

        # ---- Active object's layer (fallback) ----
        if project.active_object_id is not None:
            obj_layer_id = project.object_layer_id(project.active_object_id)
            obj_layer = project.get_layer(obj_layer_id)
            if obj_layer.asset_ref is None and not project.is_layer_effectively_locked(obj_layer_id):
                return obj_layer, False

        # ---- Source layer (last resort before creating) ----
        if any(layer.layer_id == source_layer_id for layer in project.layers):
            src = project.get_layer(source_layer_id)
            if src.node_kind is LayerNodeKind.LAYER and src.asset_ref is None:
                if not project.is_layer_effectively_locked(src.layer_id):
                    return src, False

        return (
            Layer(
                name="Objek Tempel",
                kind=LayerKind.BATIKIFIED_OBJECT,
                node_kind=LayerNodeKind.LAYER,
                properties={"object_container": True, "object_role": "clipboard"},
            ),
            True,
        )


def _referenced_asset_paths(item: LayerObject) -> set[str]:
    references: set[str] = set()
    if item.asset_ref is not None:
        references.add(item.asset_ref)
    _collect_asset_paths(item.properties, references)
    return references


def _remap_asset_values(value: object, mapping: dict[str, str]) -> object:
    """Ganti rujukan aset lama dengan yang baru, termasuk di dalam dict/list.

    Hanya string yang dapat dijadikan kunci pemetaan; nilai dict/list ditelusuri
    isinya. Tanpa penelusuran ini, salinan objek hasil AI menyimpan rujukan ke
    aset proyek asal yang bisa tidak ada di proyek tujuan.
    """

    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, dict):
        return {key: _remap_asset_values(nested, mapping) for key, nested in value.items()}
    if isinstance(value, list):
        return [_remap_asset_values(nested, mapping) for nested in value]
    if isinstance(value, tuple):
        return tuple(_remap_asset_values(nested, mapping) for nested in value)
    return value


def _collect_asset_paths(value: object, references: set[str]) -> None:
    """Telusuri properti bersarang agar aset di dalam dict/list ikut disalin."""

    if isinstance(value, str):
        if value.startswith("assets/"):
            references.add(value)
        return
    if isinstance(value, dict):
        for nested in value.values():
            _collect_asset_paths(nested, references)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _collect_asset_paths(nested, references)


def _copy_name(name: str) -> str:
    suffix = " salinan"
    maximum = max(1, 120 - len(suffix))
    return f"{name[:maximum].rstrip()}{suffix}"


__all__ = [
    "ClipboardProjectSession",
    "ObjectClipboardSnapshot",
]
