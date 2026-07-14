"""Final object-tree commands for editable Batik assets and atomic cap placement."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Transform,
)
from batikcraft_studio.imaging.batik_asset import ASSET_CATEGORIES
from batikcraft_studio.imaging.isen import (
    ISEN_LABELS,
    MASTER_CAP_SIZE,
    IsenError,
    render_isen_cap,
    symmetry_placements,
    validate_cap_size,
)
from batikcraft_studio.imaging.motif import (
    DEFAULT_MOTIF_ISEN,
    MASTER_MOTIF_SIZE,
    MOTIF_LABELS,
    MotifError,
    render_motif_cap,
    validate_motif_size,
)

from .motif_session import MotifCapError
from .object_session import ObjectProjectSession
from .session import LayerLockedError, ProjectSessionError


class EditableObjectProjectSession(ObjectProjectSession):
    """Expose atomic object-layer, metadata, ordering, and cap commands."""

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

    def move_object_up(self, object_id: str) -> bool:
        project = self.require_project()
        self._require_unlocked_object(object_id)
        layer = project.get_layer(project.object_layer_id(object_id))
        index = next(
            number for number, item in enumerate(layer.objects) if item.object_id == object_id
        )
        if index >= len(layer.objects) - 1:
            return False
        self._commit_mutation(lambda: project.reorder_object(object_id, index + 1))
        return True

    def move_object_down(self, object_id: str) -> bool:
        project = self.require_project()
        self._require_unlocked_object(object_id)
        layer = project.get_layer(project.object_layer_id(object_id))
        index = next(
            number for number, item in enumerate(layer.objects) if item.object_id == object_id
        )
        if index <= 0:
            return False
        self._commit_mutation(lambda: project.reorder_object(object_id, index - 1))
        return True

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
        self._commit_mutation(lambda: project.add_object(layer_id, duplicate, select=True))
        return duplicate

    def delete_layer_tree(self, layer_id: str) -> tuple[Layer, ...]:
        project = self.require_project()
        root = project.get_layer(layer_id)
        if project.is_layer_effectively_locked(layer_id):
            raise LayerLockedError(f"Lapis {root.name!r} sedang dikunci.")
        descendants = project.descendants_of(layer_id)
        depth_cache: dict[str, int] = {root.layer_id: 0}

        def depth(layer: Layer) -> int:
            if layer.layer_id in depth_cache:
                return depth_cache[layer.layer_id]
            value = 1 + depth(project.get_layer(layer.parent_id)) if layer.parent_id else 0
            depth_cache[layer.layer_id] = value
            return value

        targets = sorted((*descendants, root), key=depth, reverse=True)
        removed: list[Layer] = []

        def mutation() -> None:
            for layer in targets:
                removed.append(project.remove_layer(layer.layer_id))
            self._remove_unreferenced_assets()

        self._commit_mutation(mutation)
        return tuple(removed)

    def cap_isen(
        self,
        isen_type: str,
        position: tuple[float, float],
        *,
        ukuran: float = 72.0,
        warna: str = "#7A3E2A",
        susun: str = "tunggal",
        target_layer_id: str | None = None,
    ) -> tuple[LayerObject, ...]:
        project = self.require_project()
        try:
            cap_size = validate_cap_size(ukuran)
            content = render_isen_cap(isen_type, color=warna)
            placements = symmetry_placements(
                position,
                canvas_width=project.canvas.width,
                canvas_height=project.canvas.height,
                susun=susun,
            )
        except IsenError as exc:
            raise ProjectSessionError(str(exc)) from exc
        target, add_target = self._prepare_cap_layer(
            target_layer_id,
            name="Isen-Isen",
            role="isen-isen",
        )
        label = ISEN_LABELS[isen_type]
        sequence = 1 + sum(
            item.properties.get("motif_role") == "isen-isen"
            and item.properties.get("isen_type") == isen_type
            for layer in project.layers
            for item in layer.objects
        )
        asset_ref = f"assets/{uuid4()}.png"
        display_scale = cap_size / MASTER_CAP_SIZE
        objects = tuple(
            LayerObject(
                name=(
                    f"{label} {sequence} {index}"
                    if len(placements) > 1
                    else f"{label} {sequence}"
                )[:120],
                kind=ObjectKind.ISEN,
                asset_ref=asset_ref,
                transform=Transform(
                    x=placement.x,
                    y=placement.y,
                    rotation_degrees=placement.rotation_degrees,
                    scale_x=-display_scale if placement.mirror_x else display_scale,
                    scale_y=-display_scale if placement.mirror_y else display_scale,
                ),
                bounds=ObjectBounds(MASTER_CAP_SIZE, MASTER_CAP_SIZE),
                properties={
                    "source_format": "CAP_ISEN",
                    "motif_role": "isen-isen",
                    "isen_type": isen_type,
                    "isen_label": label,
                    "ukuran_cap": cap_size,
                    "warna_isen": warna.upper(),
                    "pola_susun": susun,
                    "susun_index": index,
                    "susun_count": len(placements),
                    "source_asset_ref": asset_ref,
                    "asset_category": "isen-isen",
                    "humanized": False,
                },
            )
            for index, placement in enumerate(placements, start=1)
        )

        def mutation() -> None:
            if add_target:
                project.add_layer(target, select=False)
            self._assets[asset_ref] = content
            for item in objects:
                project.add_object(target.layer_id, item, select=True)

        self._commit_mutation(mutation)
        return objects

    def cap_motif(
        self,
        motif_type: str,
        position: tuple[float, float],
        *,
        ukuran: float = 220.0,
        warna_motif: str = "#4E2A1E",
        warna_isen: str = "#8B5A2B",
        isen_type: str | None = None,
        isi_isen_otomatis: bool = True,
        susun: str = "tunggal",
        target_layer_id: str | None = None,
    ) -> tuple[LayerObject, ...]:
        project = self.require_project()
        selected_isen = isen_type or DEFAULT_MOTIF_ISEN.get(motif_type)
        if selected_isen is None:
            raise MotifCapError(f"Motif pokok tidak didukung: {motif_type!r}.")
        try:
            motif_size = validate_motif_size(ukuran)
            content = render_motif_cap(
                motif_type,
                motif_color=warna_motif,
                isen_color=warna_isen,
                isen_type=selected_isen,
                auto_isen=isi_isen_otomatis,
            )
            placements = symmetry_placements(
                position,
                canvas_width=project.canvas.width,
                canvas_height=project.canvas.height,
                susun=susun,
            )
        except (MotifError, IsenError) as exc:
            raise MotifCapError(str(exc)) from exc
        target, add_target = self._prepare_cap_layer(
            target_layer_id,
            name="Motif Pokok",
            role="motif-pokok",
        )
        motif_label = MOTIF_LABELS[motif_type]
        isen_label = ISEN_LABELS[selected_isen]
        sequence = 1 + sum(
            item.properties.get("motif_role") == "motif-pokok"
            and item.properties.get("motif_type") == motif_type
            for layer in project.layers
            for item in layer.objects
        )
        asset_ref = f"assets/{uuid4()}.png"
        display_scale = motif_size / MASTER_MOTIF_SIZE
        objects = tuple(
            LayerObject(
                name=(
                    f"{motif_label} {sequence} {index}"
                    if len(placements) > 1
                    else f"{motif_label} {sequence}"
                )[:120],
                kind=ObjectKind.MOTIF,
                asset_ref=asset_ref,
                transform=Transform(
                    x=placement.x,
                    y=placement.y,
                    rotation_degrees=placement.rotation_degrees,
                    scale_x=-display_scale if placement.mirror_x else display_scale,
                    scale_y=-display_scale if placement.mirror_y else display_scale,
                ),
                bounds=ObjectBounds(MASTER_MOTIF_SIZE, MASTER_MOTIF_SIZE),
                properties={
                    "source_format": "CAP_MOTIF_BATIK",
                    "motif_role": "motif-pokok",
                    "motif_type": motif_type,
                    "motif_label": motif_label,
                    "ukuran_motif": motif_size,
                    "warna_motif": warna_motif.upper(),
                    "isen_type": selected_isen,
                    "isen_label": isen_label,
                    "warna_isen": warna_isen.upper(),
                    "isi_isen_otomatis": bool(isi_isen_otomatis),
                    "pola_susun": susun,
                    "susun_index": index,
                    "susun_count": len(placements),
                    "source_asset_ref": asset_ref,
                    "asset_category": "motif-pokok",
                    "humanized": False,
                },
            )
            for index, placement in enumerate(placements, start=1)
        )

        def mutation() -> None:
            if add_target:
                project.add_layer(target, select=False)
            self._assets[asset_ref] = content
            for item in objects:
                project.add_object(target.layer_id, item, select=True)

        self._commit_mutation(mutation)
        return objects

    def _prepare_cap_layer(
        self,
        target_layer_id: str | None,
        *,
        name: str,
        role: str,
    ) -> tuple[Layer, bool]:
        project = self.require_project()
        if target_layer_id is not None:
            target = project.get_layer(target_layer_id)
            if target.node_kind is LayerNodeKind.GROUP:
                raise ProjectSessionError("Cap tidak dapat dimasukkan langsung ke folder.")
            if project.is_layer_effectively_locked(target.layer_id):
                raise LayerLockedError(f"Lapis {target.name!r} sedang dikunci.")
            return target, False
        if project.active_layer_id is not None:
            active = project.get_layer(project.active_layer_id)
            if (
                active.node_kind is LayerNodeKind.LAYER
                and active.asset_ref is None
                and not project.is_layer_effectively_locked(active.layer_id)
                and active.properties.get("object_container") is True
            ):
                return active, False
        for layer in project.layers:
            if (
                layer.properties.get("object_role") == role
                and layer.node_kind is LayerNodeKind.LAYER
                and not project.is_layer_effectively_locked(layer.layer_id)
            ):
                return layer, False
        return (
            Layer(
                name=name,
                kind=LayerKind.BATIKIFIED_OBJECT,
                node_kind=LayerNodeKind.LAYER,
                properties={"object_container": True, "object_role": role},
            ),
            True,
        )


__all__ = ["EditableObjectProjectSession"]
