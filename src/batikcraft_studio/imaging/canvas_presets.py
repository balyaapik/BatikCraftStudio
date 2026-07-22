"""Preset ukuran kanvas untuk dialog Dokumen Baru & Ubah Ukuran Kanvas."""

from __future__ import annotations

from dataclasses import dataclass

from batikcraft_studio.imaging.raster_layer import MAX_RASTER_DIMENSION


@dataclass(frozen=True)
class CanvasPreset:
    key: str
    label: str
    width: int
    height: int

    @property
    def megabytes_per_layer(self) -> float:
        return self.width * self.height * 4 / (1024 * 1024)


#: Preset resmi. 300 dpi untuk ukuran cetak.
CANVAS_PRESETS: tuple[CanvasPreset, ...] = (
    CanvasPreset("layar", "Layar / Web (2048×2048)", 2048, 2048),
    CanvasPreset("a4", "Cetak A4 300dpi (2480×3508)", 2480, 3508),
    CanvasPreset("a4_landscape", "Cetak A4 mendatar (3508×2480)", 3508, 2480),
    CanvasPreset("a3", "Cetak A3 300dpi (3508×4961)", 3508, 4961),
    CanvasPreset("kain", "Kain 1m 150dpi (5906×5906)", 5906, 5906),
)

DEFAULT_PRESET_KEY = "layar"


def preset_by_key(key: str) -> CanvasPreset | None:
    for preset in CANVAS_PRESETS:
        if preset.key == key:
            return preset
    return None


def clamp_dimension(value: int) -> int:
    """Jepit ukuran bebas ke rentang yang sah."""

    try:
        number = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(MAX_RASTER_DIMENSION, number))


def estimate_document_megabytes(width: int, height: int, layer_count: int) -> float:
    """Perkiraan memori dokumen — dipakai dialog untuk memperingatkan pengguna."""

    per_layer = width * height * 4 / (1024 * 1024)
    return per_layer * max(1, int(layer_count))


__all__ = [
    "CANVAS_PRESETS",
    "DEFAULT_PRESET_KEY",
    "CanvasPreset",
    "clamp_dimension",
    "estimate_document_megabytes",
    "preset_by_key",
]
