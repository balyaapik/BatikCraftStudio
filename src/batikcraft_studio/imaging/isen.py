"""Procedural batik isen-isen caps and symmetry placement helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageColor, ImageDraw

ISEN_TYPES = (
    "cecek",
    "cecek_telu",
    "sawut",
    "cecek_sawut",
    "ukel",
    "galaran",
    "sisik",
    "cacah_gori",
)
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
    "cecek_telu": "Cecek Telu",
    "sawut": "Sawut",
    "cecek_sawut": "Cecek Sawut",
    "ukel": "Ukel",
    "galaran": "Galaran",
    "sisik": "Sisik",
    "cacah_gori": "Cacah Gori",
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
    """Render one transparent antialiased PNG tile for a batik isen preset."""

    kind = _validate_isen_type(isen_type)
    rgb = _validate_color(color)
    if isinstance(size, bool) or not isinstance(size, int) or not 32 <= size <= 1024:
        raise IsenError("Ukuran sumber cap harus berupa bilangan bulat antara 32 dan 1024 piksel.")

    supersample = 4
    work_size = size * supersample
    image = Image.new("RGBA", (work_size, work_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    ink = (*rgb, 255)

    drawers = {
        "cecek": _draw_cecek,
        "cecek_telu": _draw_cecek_telu,
        "sawut": _draw_sawut,
        "cecek_sawut": _draw_cecek_sawut,
        "ukel": _draw_ukel,
        "galaran": _draw_galaran,
        "sisik": _draw_sisik,
        "cacah_gori": _draw_cacah_gori,
    }
    drawers[kind](draw, work_size, ink)

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
    radius = size * 0.018
    spacing = size / 6
    for row in range(5):
        offset = spacing * 0.5 if row % 2 else 0.0
        for column in range(5):
            x = spacing + column * spacing + offset
            if x >= size - spacing * 0.4:
                continue
            y = spacing + row * spacing
            _dot(draw, x, y, radius, color)


def _draw_cecek_telu(
    draw: ImageDraw.ImageDraw,
    size: int,
    color: tuple[int, int, int, int],
) -> None:
    radius = size * 0.016
    group = size / 3
    for row in range(3):
        for column in range(3):
            cx = group * (column + 0.5)
            cy = group * (row + 0.5)
            spread = size * 0.035
            _dot(draw, cx, cy - spread, radius, color)
            _dot(draw, cx - spread, cy + spread, radius, color)
            _dot(draw, cx + spread, cy + spread, radius, color)


def _draw_sawut(draw: ImageDraw.ImageDraw, size: int, color: tuple[int, int, int, int]) -> None:
    for row in range(3):
        for column in range(3):
            origin_x = size * (0.18 + column * 0.31)
            origin_y = size * (0.20 + row * 0.31)
            _draw_sawut_group(draw, origin_x, origin_y, size * 0.16, color, with_cecek=False)


def _draw_cecek_sawut(
    draw: ImageDraw.ImageDraw,
    size: int,
    color: tuple[int, int, int, int],
) -> None:
    for row in range(3):
        for column in range(3):
            origin_x = size * (0.17 + column * 0.32)
            origin_y = size * (0.20 + row * 0.31)
            _draw_sawut_group(draw, origin_x, origin_y, size * 0.15, color, with_cecek=True)


def _draw_ukel(draw: ImageDraw.ImageDraw, size: int, color: tuple[int, int, int, int]) -> None:
    for row in range(2):
        for column in range(2):
            center_x = size * (0.28 + column * 0.44)
            center_y = size * (0.28 + row * 0.44)
            _draw_spiral(draw, center_x, center_y, size * 0.16, color, clockwise=(row + column) % 2 == 0)


def _draw_galaran(
    draw: ImageDraw.ImageDraw,
    size: int,
    color: tuple[int, int, int, int],
) -> None:
    width = max(2, round(size * 0.012))
    gap = size * 0.105
    for index in range(-3, 9):
        offset = index * gap
        draw.line(
            (offset, size * 0.08, offset + size * 0.86, size * 0.94),
            fill=color,
            width=width,
        )


def _draw_sisik(draw: ImageDraw.ImageDraw, size: int, color: tuple[int, int, int, int]) -> None:
    width = max(2, round(size * 0.012))
    cell = size / 5
    for row in range(6):
        offset = -cell / 2 if row % 2 else 0.0
        y = row * cell - cell * 0.15
        for column in range(6):
            x = column * cell + offset
            draw.arc(
                (x, y, x + cell, y + cell),
                start=180,
                end=360,
                fill=color,
                width=width,
            )


def _draw_cacah_gori(
    draw: ImageDraw.ImageDraw,
    size: int,
    color: tuple[int, int, int, int],
) -> None:
    width = max(2, round(size * 0.01))
    spacing = size / 8
    for row in range(7):
        for column in range(7):
            cx = spacing * (column + 1)
            cy = spacing * (row + 1)
            selector = (row * 5 + column * 3) % 4
            if selector == 0:
                _dot(draw, cx, cy, size * 0.012, color)
            else:
                angle = (-35, 15, 55, 95)[selector]
                length = size * (0.035 + 0.008 * ((row + column) % 3))
                radians = math.radians(angle)
                dx = math.cos(radians) * length
                dy = math.sin(radians) * length
                draw.line((cx - dx, cy - dy, cx + dx, cy + dy), fill=color, width=width)


def _draw_sawut_group(
    draw: ImageDraw.ImageDraw,
    origin_x: float,
    origin_y: float,
    length: float,
    color: tuple[int, int, int, int],
    *,
    with_cecek: bool,
) -> None:
    base_width = max(2.0, length * 0.085)
    for index, angle in enumerate((-24, -8, 8, 24)):
        radians = math.radians(angle)
        start_x = origin_x
        start_y = origin_y + index * base_width * 0.85
        end_x = start_x + math.cos(radians) * length
        end_y = start_y + math.sin(radians) * length
        normal_x = -math.sin(radians) * base_width / 2
        normal_y = math.cos(radians) * base_width / 2
        draw.polygon(
            (
                (start_x - normal_x, start_y - normal_y),
                (start_x + normal_x, start_y + normal_y),
                (end_x + normal_x * 0.25, end_y + normal_y * 0.25),
                (end_x - normal_x * 0.25, end_y - normal_y * 0.25),
            ),
            fill=color,
        )
        if with_cecek:
            _dot(draw, end_x + length * 0.11, end_y, base_width * 0.65, color)


def _draw_spiral(
    draw: ImageDraw.ImageDraw,
    center_x: float,
    center_y: float,
    radius: float,
    color: tuple[int, int, int, int],
    *,
    clockwise: bool,
) -> None:
    points: list[tuple[float, float]] = []
    direction = 1.0 if clockwise else -1.0
    for index in range(72):
        progress = index / 71
        angle = direction * progress * math.tau * 1.65
        distance = radius * (0.12 + 0.88 * progress)
        points.append(
            (
                center_x + math.cos(angle) * distance,
                center_y + math.sin(angle) * distance,
            )
        )
    draw.line(points, fill=color, width=max(2, round(radius * 0.14)), joint="curve")
    tail_x, tail_y = points[-1]
    draw.line(
        (tail_x, tail_y, tail_x + radius * 0.5, tail_y + radius * 0.22),
        fill=color,
        width=max(2, round(radius * 0.12)),
    )


def _dot(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    radius: float,
    color: tuple[int, int, int, int],
) -> None:
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
