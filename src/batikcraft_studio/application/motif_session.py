"""Motif-pokok object commands layered on top of Cap Isen sessions."""

from __future__ import annotations

from uuid import uuid4

from batikcraft_studio.domain import LayerObject, ObjectBounds, ObjectKind, Transform
from batikcraft_studio.imaging.isen import ISEN_LABELS, IsenError, symmetry_placements
from batikcraft_studio.imaging.motif import (
    DEFAULT_MOTIF_ISEN,
    MASTER_MOTIF_SIZE,
    MOTIF_LABELS,
    MotifError,
    render_motif_cap,
    validate_motif_size,
)

from .batik_session import BatikProjectSession
from .session import ProjectSessionError


class MotifCapError(ProjectSessionError):
    """Raised when a motif-pokok cap cannot be created safely."""


class MotifProjectSession(BatikProjectSession):
    """Extend batik sessions with multi-object motif caps and automatic isen."""

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
        """Create a complete motif arrangement inside one editable layer."""

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

        target = self._ensure_batik_object_layer(
            role="motif-pokok",
            name="Motif Pokok",
            target_layer_id=target_layer_id,
        )
        motif_label = MOTIF_LABELS[motif_type]
        isen_label = ISEN_LABELS[selected_isen]
        sequence = (
            sum(
                item.properties.get("motif_role") == "motif-pokok"
                and item.properties.get("motif_type") == motif_type
                for layer in project.layers
                for item in layer.objects
            )
            + 1
        )
        asset_ref = f"assets/{uuid4()}.png"
        display_scale = motif_size / MASTER_MOTIF_SIZE
        objects: list[LayerObject] = []
        for index, placement in enumerate(placements, start=1):
            suffix = f" {index}" if len(placements) > 1 else ""
            objects.append(
                LayerObject(
                    name=f"{motif_label} {sequence}{suffix}"[:120],
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
                    },
                )
            )

        def mutation() -> None:
            self._assets[asset_ref] = content
            for item in objects:
                project.add_object(target.layer_id, item, select=True)

        self._commit_mutation(mutation)
        return tuple(objects)

    def cap_motif_di_tengah(
        self,
        motif_type: str,
        *,
        ukuran: float = 220.0,
        warna_motif: str = "#4E2A1E",
        warna_isen: str = "#8B5A2B",
        isen_type: str | None = None,
        isi_isen_otomatis: bool = True,
        susun: str = "tunggal",
        target_layer_id: str | None = None,
    ) -> tuple[LayerObject, ...]:
        """Create a complete motif at the center of the project canvas."""

        project = self.require_project()
        return self.cap_motif(
            motif_type,
            (project.canvas.width / 2, project.canvas.height / 2),
            ukuran=ukuran,
            warna_motif=warna_motif,
            warna_isen=warna_isen,
            isen_type=isen_type,
            isi_isen_otomatis=isi_isen_otomatis,
            susun=susun,
            target_layer_id=target_layer_id,
        )


__all__ = ["MotifCapError", "MotifProjectSession"]
