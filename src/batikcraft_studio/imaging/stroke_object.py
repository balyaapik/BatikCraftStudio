"""Create tightly cropped editable brush and eraser stroke assets."""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from batikcraft_studio.imaging.paint import (
    PaintStrokeError,
    apply_paint_stroke,
    create_transparent_canvas_png,
)


@dataclass(frozen=True, slots=True)
class CroppedStroke:
    """PNG bytes and project-space bounds for one completed stroke."""

    content: bytes
    left: int
    top: int
    width: int
    height: int

    @property
    def center(self) -> tuple[float, float]:
        return (self.left + self.width / 2, self.top + self.height / 2)


def _stroke_region(
    points,
    brush_size: float,
    canvas_width: int,
    canvas_height: int,
) -> tuple[int, int, int, int]:
    """Kotak kanvas terkecil yang pasti memuat seluruh goresan.

    Penghalusan goresan memakai rata-rata bergerak yang mempertahankan kedua
    ujung, sehingga titik hasilnya tidak pernah keluar dari cakupan titik asli.
    Karena itu kotak dari titik mentah, dilebarkan sejari-jari kuas, sudah pasti
    menjadi himpunan induk yang aman.
    """
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    if not xs:
        raise PaintStrokeError("Stroke has no points.")
    # Dua piksel tambahan menampung tepi anti-aliasing kuas lunak.
    radius = brush_size / 2.0 + 2.0
    left = max(0, int(math.floor(min(xs) - radius)))
    top = max(0, int(math.floor(min(ys) - radius)))
    right = min(canvas_width, int(math.ceil(max(xs) + radius)))
    bottom = min(canvas_height, int(math.ceil(max(ys) + radius)))
    if right <= left or bottom <= top:
        raise PaintStrokeError("Stroke does not intersect the project canvas.")
    return left, top, right, bottom


def render_cropped_stroke(
    *,
    canvas_width: int,
    canvas_height: int,
    points: tuple[tuple[float, float], ...] | list[tuple[float, float]],
    brush_size: float,
    color: str,
    opacity: float,
    hardness: float,
    smoothing: float,
    eraser: bool = False,
) -> CroppedStroke:
    """Render one stroke and crop transparent padding around its actual marks.

    Goresan hanya dirender pada kotak yang benar-benar disentuhnya, bukan pada
    seluruh kanvas. Versi sebelumnya mengalokasikan dan mengenkode PNG sebesar
    kanvas penuh tiga kali untuk setiap coretan, sehingga pada kanvas besar satu
    goresan pendek pun menimbulkan jeda yang terasa.
    """

    region_left, region_top, region_right, region_bottom = _stroke_region(
        points, brush_size, canvas_width, canvas_height
    )
    region_width = region_right - region_left
    region_height = region_bottom - region_top

    local_points = [
        (float(x) - region_left, float(y) - region_top) for x, y in points
    ]

    transparent = create_transparent_canvas_png(region_width, region_height)
    # Erasers are stored as positive alpha masks. The layer renderer subtracts this
    # alpha from earlier paint objects, preserving non-destructive editability.
    rendered = apply_paint_stroke(
        transparent,
        width=region_width,
        height=region_height,
        points=local_points,
        brush_size=brush_size,
        color="#FFFFFF" if eraser else color,
        erase=False,
        opacity=opacity,
        hardness=hardness,
        smoothing=smoothing,
    )
    with Image.open(BytesIO(rendered)) as source:
        source.load()
        image = source.convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise PaintStrokeError("Stroke does not intersect the project canvas.")
    left, top, right, bottom = bbox
    cropped = image.crop(bbox)
    output = BytesIO()
    # compress_level 1 jauh lebih cepat daripada optimize penuh dan selisih
    # ukurannya kecil untuk potongan goresan yang memang sudah rapat.
    cropped.save(output, format="PNG", compress_level=1)
    return CroppedStroke(
        content=output.getvalue(),
        left=region_left + left,
        top=region_top + top,
        width=right - left,
        height=bottom - top,
    )


__all__ = ["CroppedStroke", "render_cropped_stroke"]
