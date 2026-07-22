"""Dokumen raster: kumpulan RasterLayer + ukuran kanvas + latar.

Ini model dokumen untuk kanvas gaya MS Paint. Tidak ada objek — hanya layer
bitmap berurutan. Pustaka dan cetak berasal dari perataan seluruh dokumen ini,
bukan dari objek per objek.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from PIL import Image

from batikcraft_studio.imaging.raster_layer import (
    RasterLayer,
    RasterLayerError,
    flatten_layers,
)

_HEX = "0123456789abcdefABCDEF"


def _valid_hex(color: str) -> bool:
    return (
        isinstance(color, str)
        and len(color) == 7
        and color[0] == "#"
        and all(ch in _HEX for ch in color[1:])
    )


@dataclass
class RasterDocument:
    """Dokumen bitmap berlapis dengan ukuran kanvas yang bisa diubah."""

    width: int
    height: int
    background_color: str = "#FFFFFF"
    layers: list[RasterLayer] = field(default_factory=list)
    active_index: int = 0

    def __post_init__(self) -> None:
        if not _valid_hex(self.background_color):
            raise RasterLayerError("Warna latar harus format #RRGGBB.")
        self.background_color = self.background_color.upper()
        if not self.layers:
            self.layers = [RasterLayer(self.width, self.height, name="Layer 1")]
        for layer in self.layers:
            if (layer.width, layer.height) != (self.width, self.height):
                raise RasterLayerError(
                    "Setiap layer harus seukuran kanvas dokumen."
                )
        self.active_index = max(0, min(self.active_index, len(self.layers) - 1))

    # ------------------------------------------------------------------
    # Layer aktif
    # ------------------------------------------------------------------

    @property
    def active_layer(self) -> RasterLayer:
        return self.layers[self.active_index]

    def set_active(self, layer_id: str) -> None:
        for index, layer in enumerate(self.layers):
            if layer.layer_id == layer_id:
                self.active_index = index
                return
        raise RasterLayerError(f"Layer tidak ditemukan: {layer_id}")

    # ------------------------------------------------------------------
    # Kelola layer
    # ------------------------------------------------------------------

    def add_layer(self, name: str | None = None, *, above: bool = True) -> RasterLayer:
        layer = RasterLayer(
            self.width, self.height, name=name or f"Layer {len(self.layers) + 1}"
        )
        insert_at = self.active_index + 1 if above else self.active_index
        self.layers.insert(insert_at, layer)
        self.active_index = insert_at
        return layer

    def remove_active(self) -> None:
        if len(self.layers) <= 1:
            raise RasterLayerError("Dokumen harus punya minimal satu layer.")
        del self.layers[self.active_index]
        self.active_index = max(0, self.active_index - 1)

    def move_active(self, delta: int) -> None:
        target = max(0, min(len(self.layers) - 1, self.active_index + delta))
        if target == self.active_index:
            return
        layer = self.layers.pop(self.active_index)
        self.layers.insert(target, layer)
        self.active_index = target

    # ------------------------------------------------------------------
    # Ubah ukuran kanvas (pertahankan piksel)
    # ------------------------------------------------------------------

    def resize_canvas(self, width: int, height: int, *, anchor: str = "nw") -> None:
        """Ubah ukuran kanvas + semua layer, piksel dipertahankan."""

        self.layers = [
            layer.resized_canvas(width, height, anchor=anchor) for layer in self.layers
        ]
        self.width = self.layers[0].width
        self.height = self.layers[0].height

    # ------------------------------------------------------------------
    # Perataan (pustaka & cetak)
    # ------------------------------------------------------------------

    def flatten(self) -> Image.Image:
        return flatten_layers(self.layers, self.width, self.height, self.background_color)

    def flatten_active_and_below(self) -> Image.Image:
        """Meratakan sampai layer aktif — dipakai saat ganti layer (MS Paint)."""

        return flatten_layers(
            self.layers[: self.active_index + 1],
            self.width,
            self.height,
            self.background_color,
        )


__all__ = ["RasterDocument"]
