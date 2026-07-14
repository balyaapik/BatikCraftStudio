"""Batik isen-object commands layered on top of shape-enabled sessions."""

from __future__ import annotations

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
from batikcraft_studio.imaging.isen import (
    ISEN_LABELS,
    MASTER_CAP_SIZE,
    IsenError,
    render_isen_cap,
    symmetry_placements,
    validate_cap_size,
)

from .session import LayerLockedError, ProjectSessionError
from .shape_session import ShapeProjectSession


class CapIsenError(ProjectSessionError):
    """Raised when a Cap Isen command cannot be applied safely."""


class BatikProjectSession(ShapeProjectSession):
    """Extend shape sessions with multi-object Cap Isen operations."""

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
        """Apply one isen arrangement into one layer as one undoable command."""

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
            raise CapIsenError(str(exc)) from exc

        target, add_target = self._prepare_isen_layer(target_layer_id)
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

    def cap_isen_di_tengah(
        self,
        isen_type: str,
        *,
        ukuran: float = 72.0,
        warna: str = "#7A3E2A",
        susun: str = "tunggal",
        target_layer_id: str | None = None,
    ) -> tuple[LayerObject, ...]:
        project = self.require_project()
        return self.cap_isen(
            isen_type,
            (project.canvas.width / 2, project.canvas.height / 2),
            ukuran=ukuran,
            warna=warna,
            susun=susun,
            target_layer_id=target_layer_id,
        )

    def _prepare_isen_layer(self, target_layer_id: str | None) -> tuple[Layer, bool]:
        project = self.require_project()
        if target_layer_id is not None:
            target = project.get_layer(target_layer_id)
            if target.node_kind is LayerNodeKind.GROUP:
                raise CapIsenError("Cap Isen tidak dapat dimasukkan langsung ke folder.")
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
                layer.properties.get("object_role") == "isen-isen"
                and layer.node_kind is LayerNodeKind.LAYER
                and not project.is_layer_effectively_locked(layer.layer_id)
            ):
                return layer, False
        return (
            Layer(
                name="Isen-Isen",
                kind=LayerKind.BATIKIFIED_OBJECT,
                node_kind=LayerNodeKind.LAYER,
                properties={
                    "object_container": True,
                    "object_role": "isen-isen",
                },
            ),
            True,
        )


__all__ = ["BatikProjectSession", "CapIsenError"]
