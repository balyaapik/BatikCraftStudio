"""Mesin kuas raster: mengecap goresan ke bitmap layer.

Logika murni (tanpa Tk) supaya bisa diuji. Menggambar = mengecap lingkaran
kuas di sepanjang jalur titik, langsung ke bitmap layer aktif. Biayanya
sebanding dengan panjang goresan dan besar kuas — bukan dengan isi kanvas.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, hypot

from PIL import Image, ImageColor, ImageDraw

from batikcraft_studio.imaging.raster_layer import RasterLayer


@dataclass(frozen=True)
class BrushSettings:
    size: float = 12.0
    color: str = "#1A140A"
    hardness: float = 1.0  # 1.0 = tepi tajam; <1 = tepi lembut
    opacity: float = 1.0
    erase: bool = False


def _stamp(size: int, rgba: tuple[int, int, int, int], hardness: float) -> Image.Image:
    """Satu cap kuas bulat, di-cache oleh pemanggil."""

    diameter = max(1, size)
    stamp = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    draw = ImageDraw.Draw(stamp)
    draw.ellipse((0, 0, diameter - 1, diameter - 1), fill=rgba)
    if hardness < 1.0 and diameter >= 4:
        # Tepi lembut: buramkan kanal alfa.
        from PIL import ImageFilter

        radius = max(0.5, (1.0 - hardness) * diameter * 0.25)
        alpha = stamp.getchannel("A").filter(ImageFilter.GaussianBlur(radius))
        stamp.putalpha(alpha)
    return stamp


def _points_along(
    start: tuple[float, float], end: tuple[float, float], spacing: float
) -> list[tuple[float, float]]:
    """Titik-titik cap dari start ke end agar goresan mulus, tanpa celah."""

    distance = hypot(end[0] - start[0], end[1] - start[1])
    steps = max(1, int(ceil(distance / max(spacing, 0.5))))
    return [
        (
            start[0] + (end[0] - start[0]) * i / steps,
            start[1] + (end[1] - start[1]) * i / steps,
        )
        for i in range(1, steps + 1)
    ]


class BrushEngine:
    """Mengecap goresan ke sebuah RasterLayer."""

    def __init__(self, settings: BrushSettings) -> None:
        self.settings = settings
        diameter = max(1, int(round(settings.size)))
        rgb = ImageColor.getrgb(settings.color)
        alpha = max(0, min(255, int(round(settings.opacity * 255))))
        self._stamp = _stamp(diameter, (*rgb, alpha), settings.hardness)
        self._alpha_stamp = self._stamp.getchannel("A")
        self._radius = diameter / 2
        # Jarak antar cap: rapat supaya tidak berlubang.
        self._spacing = max(1.0, diameter * 0.25)

    def stamp_point(self, layer: RasterLayer, x: float, y: float) -> None:
        left = int(round(x - self._radius))
        top = int(round(y - self._radius))
        if self.settings.erase:
            layer.erase(self._alpha_stamp, (left, top))
        else:
            layer.composite(self._stamp, (left, top))

    def stroke(self, layer: RasterLayer, points: list[tuple[float, float]]) -> None:
        """Cap seluruh goresan. Satu titik = satu titik; banyak = jalur mulus."""

        if not points:
            return
        self.stamp_point(layer, points[0][0], points[0][1])
        for start, end in zip(points, points[1:]):
            for px, py in _points_along(start, end, self._spacing):
                self.stamp_point(layer, px, py)


__all__ = ["BrushEngine", "BrushSettings"]
