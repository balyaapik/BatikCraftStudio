"""Procedural batik isen-isen caps and symmetry placement helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageColor, ImageDraw

ISEN_TYPES = ("cecek", "sawut", "ukel", "cecek_sawut")
SUSUN_TYPES = (
    "tunggal",
    "cermin_kiri_kanan",
    "cermin_atas_bawah",
    "cermin_empat",
    "putar_4",
    "putar_8",
)
MASTER_CAP_SIZE = 256
MIN_CAP_SIZE = 8.0
MAX_CAP_SIZE = 1024.0

ISEN_LABELS = {
    "cecek": "Cecek",
    "sawut": "Sawut",
    "ukel": "Ukel",
    "cecek_sawut": "Cecek Sawut",
}

SUSUN_LABELS = {
    "tunggal": "Tunggal",
    "cermin_kiri_kanan": "Cermin kiri–kanan",
    "cermin_atas_bawah": "Cermin atas–bawah",
    "cermin_empat": "Cermin empat arah",
    "putar_4": "Putar 4",
    "putar_8": "Putar 8",
}


class IsenError(ValueError):
    """Raised when an isen-isen cap or symmetry request is invalid."""


@dataclass(frozen=True, slots=True)
class CapPlacement:
    """One cap placement in project coordinates."""

    x: float
    y: float
    rotation_degrees: float = 0.0
    mirror_x: bool = False
    mirror_y: bool = False


def render_isen_cap(
    isen_type: str,
    *,
    color: str,
    size: int = MASTER_CAP_SIZE,
) -> bytes:
    """Render one transparent antialiased PNG cap for a batik isen preset."""

    kind = _validate_isen_type(isen_type)
    rgb = _validate_color(color)
    if isinstance(size, bool) or not isinstance(size, int) or not 32 <= size <= 1024:
        raise IsenError("Ukuran sumber cap harus berupa bilangan bulat antara 32 dan 1024 piksel.")

    supersample = 4
    work_size = size * supersample
    image = Image.new("RGBA", (work_size, work_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    ink = (*rgb, 255)

    if kind == "cecek":
        _draw_cecek(draw, work_size, ink)
    elif kind == "sawut":
        _draw_sawut(draw, work_size, ink)
    elif kind == "ukel":
        _draw_ukel(draw, work_size, ink)
    else:
        _draw_cecek_sawut(draw, work_size, ink)

    image = image.resize((size, size), Image.Resampling.LANCZOS)
    alpha = image.getchannel("A")
    image = Image.new("RGBA", (size, size), (*rgb, 0))
    image.putalpha(alpha)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def symmetry_placements(
    position: tuple[float, float],
    *,
    canvas_width: int,
    canvas_height: int,
    susun: str,
) -> tuple[CapPlacement, ...]:
    """Return deduplicated placements around the center of the kain/canvas."""

    x, y = _validate_position(position)
    if isinstance(canvas_width, bool) or not isinstance(canvas_width, int) or canvas_width < 1:
        raise IsenError("Lebar kanvas harus berupa bilangan bulat positif.")
    if isinstance(canvas_height, bool) or not isinstance(canvas_height, int) or canvas_height < 1:
        raise IsenError("Tinggi kanvas harus berupa bilangan bulat positif.")
    if not 0 <= x <= canvas_width or not 0 <= y <= canvas_height:
        raise IsenError("Posisi cap harus berada di dalam kanvas proyek.")
    mode = _validate_susun(susun)

    center_x = canvas_width / 2
    center_y = canvas_height / 2
    if mode == "tunggal":
        placements = [CapPlacement(x, y)]
    elif mode == "cermin_kiri_kanan":
        placements = [
            CapPlacement(x, y),
            CapPlacement(2 * center_x - x, y, mirror_x=True),
        ]
    elif mode == "cermin_atas_bawah":
        placements = [
            CapPlacement(x, y),
            CapPlacement(x, 2 * center_y - y, mirror_y=True),
        ]
    elif mode == "cermin_empat":
        placements = [
            CapPlacement(x, y),
            CapPlacement(2 * center_x - x, y, mirror_x=True),
            CapPlacement(x, 2 * center_y - y, mirror_y=True),
            CapPlacement(
                2 * center_x - x,
                2 * center_y - y,
                mirror_x=True,
                mirror_y=True,
            ),
        ]
    else:
        count = 4 if mode == "putar_4" else 8
        placements = []
        dx = x - center_x
        dy = y - center_y
        for index in range(count):
            angle = 360.0 * index / count
            radians = math.radians(angle)
            placements.append(
                CapPlacement(
                    center_x + dx * math.cos(radians) - dy * math.sin(radians),
                    center_y + dx * math.sin(radians) + dy * math.cos(radians),
                    rotation_degrees=angle,
                )
            )
    return _deduplicate(placements)


def validate_cap_size(value: float) -> float:
    """Validate a requested displayed cap diameter."""

    if isinstance(value, bool):
        raise IsenError("Ukuran cap harus berupa angka.")
    try:
        size = float(value)
    except (TypeError, ValueError) as exc:
        raise IsenError("Ukuran cap harus berupa angka.") from exc
    if not math.isfinite(size) or not MIN_CAP_SIZE <= size <= MAX_CAP_SIZE:
        raise IsenError(
            f"Ukuran cap harus antara {MIN_CAP_SIZE:g} dan {MAX_CAP_SIZE:g} piksel."
        )
    return size


def _draw_cecek(draw: ImageDraw.ImageDraw, size: int, color: tuple[int, int, int, int]) -> None:
    radius = size * 0.15
    center = size / 2
    draw.ellipse(
        (center - radius, center - radius, center + radius, center + radius),
        fill=color,
    )


def _draw_sawut(draw: ImageDraw.ImageDraw, size: int, color: tuple[int, int, int, int]) -> None:
    width = max(2, round(size * 0.045))
    for offset in (-0.18, 0.0, 0.18):
        y1 = size * (0.35 + offset)
        y2 = size * (0.65 + offset)
        draw.line(
            (size * 0.25, y1, size * 0.75, y2),
            fill=color,
            width=width,
        )


def _draw_ukel(draw: ImageDraw.ImageDraw, size: int, color: tuple[int, int, int, int]) -> None:
    points: list[tuple[float, float]] = []
    center = size / 2
    turns = 2.35
    for index in range(120):
        progress = index / 119
        angle = progress * turns * math.tau
        radius = size * (0.07 + 0.31 * progress)
        points.append(
            (
                center + math.cos(angle) * radius,
                center + math.sin(angle) * radius,
            )
        )
    draw.line(points, fill=color, width=max(2, round(size * 0.04)), joint="curve")


def _draw_cecek_sawut(
    draw: ImageDraw.ImageDraw,
    size: int,
    color: tuple[int, int, int, int],
) -> None:
    width = max(2, round(size * 0.035))
    for row in range(3):
        y = size * (0.32 + row * 0.18)
        draw.line((size * 0.23, y, size * 0.62, y), fill=color, width=width)
        radius = size * 0.045
        x = size * 0.75
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def _validate_color(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise IsenError("Warna isen harus berupa warna CSS yang valid.")
    try:
        rgb = ImageColor.getrgb(value)
    except (TypeError, ValueError) as exc:
        raise IsenError("Warna isen tidak valid.") from exc
    return rgb[:3]


def _validate_isen_type(value: str) -> str:
    if value not in ISEN_TYPES:
        raise IsenError(f"Jenis isen tidak didukung: {value!r}.")
    return value


def _validate_susun(value: str) -> str:
    if value not in SUSUN_TYPES:
        raise IsenError(f"Pola susun tidak didukung: {value!r}.")
    return value


def _validate_position(value: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise IsenError("Posisi cap harus berisi koordinat x dan y.")
    try:
        x, y = (float(value[0]), float(value[1]))
    except (TypeError, ValueError) as exc:
        raise IsenError("Posisi cap harus berisi angka yang valid.") from exc
    if not math.isfinite(x) or not math.isfinite(y):
        raise IsenError("Posisi cap harus berisi angka yang valid.")
    return x, y


def _deduplicate(placements: list[CapPlacement]) -> tuple[CapPlacement, ...]:
    unique: list[CapPlacement] = []
    seen: set[tuple[float, float, float, bool, bool]] = set()
    for placement in placements:
        key = (
            round(placement.x, 6),
            round(placement.y, 6),
            round(placement.rotation_degrees % 360, 6),
            placement.mirror_x,
            placement.mirror_y,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(placement)
    return tuple(unique)


__all__ = [
    "ISEN_LABELS",
    "ISEN_TYPES",
    "MASTER_CAP_SIZE",
    "SUSUN_LABELS",
    "SUSUN_TYPES",
    "CapPlacement",
    "IsenError",
    "render_isen_cap",
    "symmetry_placements",
    "validate_cap_size",
]
