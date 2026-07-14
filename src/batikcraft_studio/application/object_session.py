"""Object-tree, folder, reusable asset, and humanize application services."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Project,
    Transform,
)
from batikcraft_studio.imaging.batik_asset import (
    BatikAssetError,
    EditableBatikAsset,
    encode_batik_asset,
    humanize_raster_asset,
    load_batik_asset,
)
from batikcraft_studio.imaging.raster import normalize_raster_image

from .motif_session import MotifProjectSession
from .session import (
    LayerLockedError,
    ProjectSessionError,
    _SessionState,
)


class ObjectLockedError(ProjectSessionError):
    """Raised when an object or its ancestor layer is locked."""


class ObjectProjectSession(MotifProjectSession):
    """Final editor session with nested layers and independently editable objects."""

    def create_folder(
        self,
        name: str = "Folder Motif",
        *,
        parent_id: str | None = None,
    ) -> Layer:
        project = self.require_project()
        folder = Layer(
            name=name,
            kind=LayerKind.GROUP,
            node_kind=LayerNodeKind.GROUP,
            parent_id=parent_id,
        )
        self._commit_mutation(lambda: project.add_layer(folder))
        return folder

    def create_object_layer(
        self,
        name: str = "Lapis Motif",
        *,
        parent_id: str | None = None,
        kind: LayerKind = LayerKind.BATIKIFIED_OBJECT,
        role: str = "objects",
    ) -> Layer:
        project = self.require_project()
        layer = Layer(
            name=name,
            kind=kind,
            node_kind=LayerNodeKind.LAYER,
            parent_id=parent_id,
            properties={"object_container": True, "object_role": role},
        )
        self._commit_mutation(lambda: project.add_layer(layer))
        return layer

    def move_layer_to_folder(self, layer_id: str, folder_id: str | None) -> Layer:
        project = self.require_project()
        layer = project.get_layer(layer_id)
        if project.is_layer_effectively_locked(layer_id):
            raise LayerLockedError(f"Lapis {layer.name!r} sedang dikunci.")
        updated: Layer | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.set_layer_parent(layer_id, folder_id)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Pemindahan sublapis tidak menghasilkan perubahan.")
        return updated

    def delete_layer_tree(self, layer_id: str) -> tuple[Layer, ...]:
        """Delete a folder and all descendants as one undoable mutation."""

        project = self.require_project()
        root = project.get_layer(layer_id)
        if project.is_layer_effectively_locked(layer_id):
            raise LayerLockedError(f"Lapis {root.name!r} sedang dikunci.")
        descendants = project.descendants_of(layer_id)
        targets = (*descendants, root)
        removed: list[Layer] = []

        def mutation() -> None:
            for layer in reversed(targets):
                if project.children_of(layer.layer_id):
                    continue
                removed.append(project.remove_layer(layer.layer_id))
            if project.get_layer(root.layer_id):
                removed.append(project.remove_layer(root.layer_id))
            self._remove_unreferenced_assets()

        self._commit_mutation(mutation)
        return tuple(removed)

    def select_object(self, object_id: str | None) -> None:
        self.require_project().set_active_object(object_id)

    def import_raster_object(
        self,
        filename: str,
        content: bytes | bytearray | memoryview,
        *,
        target_layer_id: str | None = None,
    ) -> LayerObject:
        raster = normalize_raster_image(content)
        project = self.require_project()
        target, add_target = self._resolve_object_layer(target_layer_id, name="Aset Motif")
        asset_ref = f"assets/{uuid4()}.png"
        scale = min(
            1.0,
            project.canvas.width * 0.65 / raster.width,
            project.canvas.height * 0.65 / raster.height,
        )
        stem = Path(filename).stem.strip() or "Asset Motif"
        item = LayerObject(
            name=stem[:120],
            kind=ObjectKind.RASTER,
            asset_ref=asset_ref,
            transform=Transform(
                x=project.canvas.width / 2,
                y=project.canvas.height / 2,
                scale_x=scale,
                scale_y=scale,
            ),
            bounds=ObjectBounds(raster.width, raster.height),
            properties={
                "source_format": raster.source_format,
                "original_name": Path(filename).name,
                "source_asset_ref": asset_ref,
                "asset_category": "ornamen",
                "humanized": False,
            },
        )

        def mutation() -> None:
            if add_target:
                project.add_layer(target)
            self._assets[asset_ref] = raster.content
            project.add_object(target.layer_id, item, select=True)

        self._commit_mutation(mutation)
        return item

    def import_batik_asset(
        self,
        filename: str,
        content: bytes | bytearray | memoryview,
        *,
        target_layer_id: str | None = None,
        default_category: str = "ornamen",
    ) -> LayerObject:
        try:
            asset = load_batik_asset(
                content,
                filename=filename,
                default_category=default_category,
            )
        except BatikAssetError as exc:
            raise ProjectSessionError(str(exc)) from exc
        project = self.require_project()
        target, add_target = self._resolve_object_layer(target_layer_id, name="Pustaka Aset")
        source_ref = f"assets/{uuid4()}.png"
        scale = min(
            1.0,
            project.canvas.width * 0.55 / asset.width,
            project.canvas.height * 0.55 / asset.height,
        )
        if asset.category == "motif-pokok":
            kind = ObjectKind.MOTIF
        elif asset.category == "isen-isen":
            kind = ObjectKind.ISEN
        else:
            kind = ObjectKind.RASTER
        item = LayerObject(
            name=asset.name,
            kind=kind,
            asset_ref=source_ref,
            transform=Transform(
                x=project.canvas.width / 2,
                y=project.canvas.height / 2,
                scale_x=scale,
                scale_y=scale,
            ),
            bounds=ObjectBounds(asset.width, asset.height),
            properties={
                **dict(asset.metadata),
                "source_format": "BATIK_ASSET",
                "source_asset_ref": source_ref,
                "asset_category": asset.category,
                "humanized": False,
            },
        )

        def mutation() -> None:
            if add_target:
                project.add_layer(target)
            self._assets[source_ref] = asset.content
            project.add_object(target.layer_id, item, select=True)

        self._commit_mutation(mutation)
        return item

    def export_batik_asset(self, object_id: str) -> bytes:
        project = self.require_project()
        item = project.get_object(object_id)
        source_ref = item.properties.get("source_asset_ref") or item.asset_ref
        if not isinstance(source_ref, str) or source_ref not in self._assets:
            raise ProjectSessionError(
                "Objek tidak memiliki sumber asset yang dapat diekspor."
            )
        category = str(item.properties.get("asset_category", "ornamen"))
        excluded = {
            "source_asset_ref",
            "humanized_asset_ref",
            "humanized",
            "humanize_seed",
            "humanize_edge_wobble",
            "humanize_ink_breaks",
            "humanize_opacity_variation",
        }
        asset = EditableBatikAsset(
            name=item.name,
            category=category,
            content=self._assets[source_ref],
            width=round(item.bounds.width),
            height=round(item.bounds.height),
            metadata={
                key: value
                for key, value in item.properties.items()
                if key not in excluded
            },
        )
        try:
            return encode_batik_asset(asset)
        except BatikAssetError as exc:
            raise ProjectSessionError(str(exc)) from exc

    def humanize_object(
        self,
        object_id: str,
        *,
        seed: int = 2026,
        edge_wobble: float = 0.18,
        ink_breaks: float = 0.08,
        opacity_variation: float = 0.12,
    ) -> LayerObject:
        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        source_ref = item.properties.get("source_asset_ref") or item.asset_ref
        if not isinstance(source_ref, str) or source_ref not in self._assets:
            raise ProjectSessionError("Sumber asset objek tidak tersedia untuk humanize.")
        try:
            content = humanize_raster_asset(
                self._assets[source_ref],
                seed=seed,
                edge_wobble=edge_wobble,
                ink_breaks=ink_breaks,
                opacity_variation=opacity_variation,
            )
        except BatikAssetError as exc:
            raise ProjectSessionError(str(exc)) from exc
        rendered_ref = f"assets/{uuid4()}.png"
        properties = dict(item.properties)
        properties.update(
            {
                "source_asset_ref": source_ref,
                "humanized_asset_ref": rendered_ref,
                "humanized": True,
                "humanize_seed": seed,
                "humanize_edge_wobble": float(edge_wobble),
                "humanize_ink_breaks": float(ink_breaks),
                "humanize_opacity_variation": float(opacity_variation),
            }
        )
        previous_ref = item.asset_ref
        updated: LayerObject | None = None

        def mutation() -> None:
            nonlocal updated
            self._assets[rendered_ref] = content
            updated = project.update_object(
                object_id,
                asset_ref=rendered_ref,
                properties=properties,
            )
            self._remove_asset_if_unreferenced(previous_ref)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Humanize tidak menghasilkan objek baru.")
        return updated

    def reset_object_humanize(self, object_id: str) -> LayerObject:
        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        source_ref = item.properties.get("source_asset_ref")
        if not isinstance(source_ref, str) or source_ref not in self._assets:
            raise ProjectSessionError(
                "Objek tidak memiliki asset sumber untuk dipulihkan."
            )
        previous_ref = item.asset_ref
        properties = dict(item.properties)
        properties["humanized"] = False
        properties.pop("humanized_asset_ref", None)
        updated: LayerObject | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_object(
                object_id,
                asset_ref=source_ref,
                properties=properties,
            )
            self._remove_asset_if_unreferenced(previous_ref)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Reset humanize tidak menghasilkan perubahan.")
        return updated

    def update_object_transform(
        self,
        object_id: str,
        *,
        x: float | None = None,
        y: float | None = None,
        rotation_degrees: float | None = None,
        scale_x: float | None = None,
        scale_y: float | None = None,
    ) -> LayerObject:
        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        current = item.transform
        candidate = Transform(
            x=current.x if x is None else x,
            y=current.y if y is None else y,
            rotation_degrees=(
                current.rotation_degrees
                if rotation_degrees is None
                else rotation_degrees
            ),
            scale_x=current.scale_x if scale_x is None else scale_x,
            scale_y=current.scale_y if scale_y is None else scale_y,
        )
        if candidate == current:
            return item
        updated: LayerObject | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_object(object_id, transform=candidate)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Transform objek tidak menghasilkan perubahan.")
        return updated

    def move_object(self, object_id: str, *, x: float, y: float) -> LayerObject:
        return self.update_object_transform(object_id, x=x, y=y)

    def set_object_opacity(self, object_id: str, opacity: float) -> LayerObject:
        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        if float(opacity) == item.opacity:
            return item
        updated: LayerObject | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_object(object_id, opacity=opacity)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Opacity objek tidak menghasilkan perubahan.")
        return updated

    def set_object_visibility(self, object_id: str, visible: bool) -> LayerObject:
        project = self.require_project()
        current = project.get_object(object_id)
        if current.visible == visible:
            return current
        updated: LayerObject | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_object(object_id, visible=visible)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Visibility objek tidak menghasilkan perubahan.")
        return updated

    def set_object_locked(self, object_id: str, locked: bool) -> LayerObject:
        project = self.require_project()
        current = project.get_object(object_id)
        if current.locked == locked:
            return current
        updated: LayerObject | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_object(object_id, locked=locked)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Lock objek tidak menghasilkan perubahan.")
        return updated

    def duplicate_object(self, object_id: str) -> LayerObject:
        project = self.require_project()
        source = project.get_object(object_id)
        layer_id = project.object_layer_id(object_id)
        suffix = " salinan"
        duplicate = LayerObject(
            name=f"{source.name[: 120 - len(suffix)].rstrip()}{suffix}",
            kind=source.kind,
            asset_ref=source.asset_ref,
            visible=source.visible,
            locked=False,
            opacity=source.opacity,
            transform=replace(
                source.transform,
                x=source.transform.x + 24,
                y=source.transform.y + 24,
            ),
            bounds=source.bounds,
            properties=dict(source.properties),
        )
        self._commit_mutation(
            lambda: project.add_object(layer_id, duplicate, select=True)
        )
        return duplicate

    def delete_object(self, object_id: str) -> LayerObject:
        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        removed: LayerObject | None = None

        def mutation() -> None:
            nonlocal removed
            removed = project.remove_object(object_id)
            self._remove_asset_if_unreferenced(item.asset_ref)
            source_ref = item.properties.get("source_asset_ref")
            if isinstance(source_ref, str):
                self._remove_asset_if_unreferenced(source_ref)

        self._commit_mutation(mutation)
        if removed is None:
            raise ProjectSessionError("Penghapusan objek tidak menghasilkan perubahan.")
        return removed

    def move_object_to_layer(self, object_id: str, layer_id: str) -> LayerObject:
        project = self.require_project()
        self._require_unlocked_object(object_id)
        moved: LayerObject | None = None

        def mutation() -> None:
            nonlocal moved
            moved = project.move_object(object_id, layer_id)

        self._commit_mutation(mutation)
        if moved is None:
            raise ProjectSessionError("Pemindahan objek tidak menghasilkan perubahan.")
        return moved

    def _resolve_object_layer(self, layer_id: str | None, *, name: str) -> tuple[Layer, bool]:
        """Resolve an object-insertion target, respecting the active layer selection.

        Returns a ``(layer, needs_add)`` pair.  When *needs_add* is ``True`` the
        caller must call ``project.add_layer(layer)`` inside its ``_commit_mutation``
        block so that layer creation and object insertion share one undo/redo entry.

        This override of ``ShapeProjectSession._resolve_object_layer`` provides a
        richer implementation that also handles folders and uses
        ``create_object_layer`` for a proper ``BATIKIFIED_OBJECT`` container.

        1. Explicit *layer_id* → validate and use.
        2. Active layer → use if valid and unlocked; reject if locked.
        3. No active layer → create a new one (``needs_add=False``, already committed).
        """
        project = self.require_project()

        if layer_id is not None:
            candidate = project.get_layer(layer_id)
            if candidate.node_kind is not LayerNodeKind.LAYER or candidate.asset_ref is not None:
                raise LayerLockedError(
                    "The selected target is not a valid object layer."
                )
            if project.is_layer_effectively_locked(candidate.layer_id):
                raise LayerLockedError(
                    f"Layer {candidate.name!r} is locked and cannot receive new objects."
                )
            return candidate, False

        active_id = project.active_layer_id
        if active_id is not None:
            active = project.get_layer(active_id)
            if (
                active.node_kind is LayerNodeKind.LAYER
                and active.asset_ref is None
            ):
                if project.is_layer_effectively_locked(active.layer_id):
                    raise LayerLockedError(
                        f"Layer {active.name!r} is locked and cannot receive new objects. "
                        "Unlock the layer or select a different layer."
                    )
                return active, False

        return self.create_object_layer(name), False

    def _require_unlocked_layer(self, layer_id: str) -> Layer:
        project = self.require_project()
        layer = project.get_layer(layer_id)
        if project.is_layer_effectively_locked(layer_id):
            raise LayerLockedError(f"Lapis {layer.name!r} sedang dikunci.")
        return layer

    def _require_unlocked_object(self, object_id: str) -> LayerObject:
        project = self.require_project()
        item = project.get_object(object_id)
        layer_id = project.object_layer_id(object_id)
        if item.locked or project.is_layer_effectively_locked(layer_id):
            raise ObjectLockedError(f"Objek {item.name!r} sedang dikunci.")
        return item

    def _remove_asset_if_unreferenced(self, asset_ref: str | None) -> None:
        if asset_ref is None or asset_ref not in self._assets:
            return
        project = self.require_project()
        for layer in project.layers:
            if layer.asset_ref == asset_ref:
                return
            for item in layer.objects:
                if item.asset_ref == asset_ref:
                    return
                if item.properties.get("source_asset_ref") == asset_ref:
                    return
        self._assets.pop(asset_ref, None)

    def _remove_unreferenced_assets(self) -> None:
        for asset_ref in tuple(self._assets):
            self._remove_asset_if_unreferenced(asset_ref)

    def _capture_state(self) -> _SessionState:
        return _SessionState(
            project=_clone_object_project(self._project),
            path=self._path,
            assets=tuple(sorted(self._assets.items())),
        )

    def _restore_state(self, state: _SessionState) -> None:
        self._project = _clone_object_project(state.project)
        self._path = state.path
        self._assets = dict(state.assets)


def _clone_object_project(project: Project | None) -> Project | None:
    if project is None:
        return None
    return Project(
        metadata=project.metadata,
        canvas=project.canvas,
        layers=project.layers,
        project_id=project.project_id,
        schema_version=project.schema_version,
        active_layer_id=project.active_layer_id,
        active_object_id=project.active_object_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        revision=project.revision,
        saved_revision=project.saved_revision,
    )


__all__ = ["ObjectLockedError", "ObjectProjectSession"]
