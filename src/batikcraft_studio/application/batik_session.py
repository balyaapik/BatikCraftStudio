"""Batik motif-cap commands layered on top of shape-enabled project sessions."""

from __future__ import annotations

from uuid import uuid4

from batikcraft_studio.domain import Layer, LayerKind, Transform
from batikcraft_studio.imaging.isen import (
    ISEN_LABELS,
    MASTER_CAP_SIZE,
    IsenError,
    render_isen_cap,
    symmetry_placements,
    validate_cap_size,
)

from .session import ProjectSessionError
from .shape_session import ShapeProjectSession


class CapIsenError(ProjectSessionError):
    """Raised when a cap isen command cannot be applied safely."""


class BatikProjectSession(ShapeProjectSession):
    """Extend shape sessions with cap motif and batik symmetry operations."""

    def cap_isen(
        self,
        isen_type: str,
        position: tuple[float, float],
        *,
        ukuran: float = 72.0,
        warna: str = "#7A3E2A",
        susun: str = "tunggal",
    ) -> tuple[Layer, ...]:
        """Apply one isen cap arrangement as a single undoable session mutation."""

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

        label = ISEN_LABELS[isen_type]
        sequence = (
            sum(
                layer.properties.get("motif_role") == "isen-isen"
                and layer.properties.get("isen_type") == isen_type
                for layer in project.layers
            )
            + 1
        )
        asset_ref = f"assets/{uuid4()}.png"
        display_scale = cap_size / MASTER_CAP_SIZE
        layers: list[Layer] = []
        for index, placement in enumerate(placements, start=1):
            suffix = f" {index}" if len(placements) > 1 else ""
            layers.append(
                Layer(
                    name=f"{label} {sequence}{suffix}"[:120],
                    kind=LayerKind.RASTER,
                    asset_ref=asset_ref,
                    transform=Transform(
                        x=placement.x,
                        y=placement.y,
                        rotation_degrees=placement.rotation_degrees,
                        scale_x=-display_scale if placement.mirror_x else display_scale,
                        scale_y=-display_scale if placement.mirror_y else display_scale,
                    ),
                    properties={
                        "pixel_width": MASTER_CAP_SIZE,
                        "pixel_height": MASTER_CAP_SIZE,
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
            )

        def mutation() -> None:
            self._assets[asset_ref] = content
            for layer in layers:
                project.add_layer(layer)

        self._commit_mutation(mutation)
        return tuple(layers)

    def cap_isen_di_tengah(
        self,
        isen_type: str,
        *,
        ukuran: float = 72.0,
        warna: str = "#7A3E2A",
        susun: str = "tunggal",
    ) -> tuple[Layer, ...]:
        """Apply a cap arrangement at the center of the project canvas."""

        project = self.require_project()
        return self.cap_isen(
            isen_type,
            (project.canvas.width / 2, project.canvas.height / 2),
            ukuran=ukuran,
            warna=warna,
            susun=susun,
        )


__all__ = ["BatikProjectSession", "CapIsenError"]
