"""Stylized motif-pokok templates with automatic batik isen filling."""

from __future__ import annotations

import math
from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter

from .isen import ISEN_LABELS, ISEN_TYPES, IsenError, render_isen_cap

MOTIF_TYPES = ("kawung", "truntum", "ceplok", "lereng")
MOTIF_LABELS = {
    "kawung": "Kawung",
    "truntum": "Truntum",
    "ceplok": "Ceplok",
    "lereng": "Lereng",
}
DEFAULT_MOTIF_ISEN = {
    "kawung": "cecek_sawut",
    "truntum": "cecek_telu",
    "ceplok": "ukel",
    "lereng": "galaran",
}
MASTER_MOTIF_SIZE = 512
MIN_MOTIF_SIZE = 48.0
MAX_MOTIF_SIZE = 2048.0


class MotifError(ValueError):
    """Raised when a motif-pokok request is invalid."""


@lru_cache(maxsize=64)
def render_motif_cap(
    motif_type: str,
    *,
    motif_color: str,
    isen_color: str,
    isen_type: str | None = None,
    auto_isen: bool = True,
    size: int = MASTER_MOTIF_SIZE,
) -> bytes:
    """Render one transparent motif-pokok PNG with optional automatic isen filling."""

    kind = _validate_motif_type(motif_type)
    motif_rgb = _validate_color(motif_color, "Warna motif")
    isen_rgb = _validate_color(isen_color, "Warna isen")
    if isinstance(size, bool) or not isinstance(size, int) or not 128 <= size <= 512:
        raise MotifError(
            "Ukuran sumber motif harus berupa bilangan bulat antara 128 dan 512 piksel."
        )

    selected_isen = isen_type or DEFAULT_MOTIF_ISEN[kind]
    if selected_isen not in ISEN_TYPES:
        raise MotifError(f"Jenis isen tidak didukung: {selected_isen!r}.")

    supersample = 2
    work_size = size * supersample
    fill_mask = Image.new("L", (work_size, work_size), 0)
    accent_mask = Image.new("L", (work_size, work_size), 0)

    drawers = {
        "kawung": _draw_kawung_masks,
        "truntum": _draw_truntum_masks,
        "ceplok": _draw_ceplok_masks,
        "lereng": _draw_lereng_masks,
    }
    drawers[kind](fill_mask, accent_mask)

    outline_width = max(5, round(work_size * 0.012))
    outline_alpha = _outline_from_mask(fill_mask, outline_width)
    outline_alpha = ImageChops.lighter(outline_alpha, accent_mask)

    isen_alpha = Image.new("L", (work_size, work_size), 0)
    if auto_isen:
        try:
            isen_bytes = render_isen_cap(
                selected_isen,
                color=isen_color,
                size=work_size,
            )
        except IsenError as exc:
            raise MotifError(str(exc)) from exc
        with Image.open(BytesIO(isen_bytes)) as source:
            source.load()
            source_alpha = source.convert("RGBA").getchannel("A")
        isen_alpha = ImageChops.multiply(source_alpha, fill_mask)

    outline_alpha = outline_alpha.resize((size, size), Image.Resampling.LANCZOS)
    isen_alpha = isen_alpha.resize((size, size), Image.Resampling.LANCZOS)

    result = Image.new("RGBA", (size, size), (*isen_rgb, 0))
    result.putalpha(isen_alpha)
    outline = Image.new("RGBA", (size, size), (*motif_rgb, 0))
    outline.putalpha(outline_alpha)
    result.alpha_composite(outline)

    output = BytesIO()
    result.save(output, format="PNG")
    return output.getvalue()


def validate_motif_size(value: float) -> float:
    """Validate the displayed diameter of a motif-pokok cap."""

    if isinstance(value, bool):
        raise MotifError("Ukuran motif harus berupa angka.")
    try:
        size = float(value)
    except (TypeError, ValueError) as exc:
        raise MotifError("Ukuran motif harus berupa angka.") from exc
    if not math.isfinite(size) or not MIN_MOTIF_SIZE <= size <= MAX_MOTIF_SIZE:
        raise MotifError(
            f"Ukuran motif harus antara {MIN_MOTIF_SIZE:g} dan {MAX_MOTIF_SIZE:g} piksel."
        )
    return size


def motif_description(motif_type: str, isen_type: str | None = None) -> str:
    """Return a concise Indonesian label for a motif and its selected isen."""

    kind = _validate_motif_type(motif_type)
    selected = isen_type or DEFAULT_MOTIF_ISEN[kind]
    if selected not in ISEN_LABELS:
        raise MotifError(f"Jenis isen tidak didukung: {selected!r}.")
    return f"{MOTIF_LABELS[kind]} dengan isen {ISEN_LABELS[selected]}"


def _draw_kawung_masks(fill: Image.Image, accent: Image.Image) -> None:
    size = fill.width
    center = size / 2
    petals = (
        (-0.17, -0.17, 45),
        (0.17, -0.17, -45),
        (-0.17, 0.17, -45),
        (0.17, 0.17, 45),
    )
    for offset_x, offset_y, angle in petals:
        petal = _rotated_ellipse(
            size,
            center + size * offset_x,
            center + size * offset_y,
            size * 0.26,
            size * 0.48,
            angle,
        )
        fill.paste(ImageChops.lighter(fill, petal))

    draw = ImageDraw.Draw(accent)
    diamond = size * 0.095
    draw.polygon(
        (
            (center, center - diamond),
            (center + diamond, center),
            (center, center + diamond),
            (center - diamond, center),
        ),
        fill=255,
    )
    dot_radius = size * 0.018
    for x, y in (
        (center, center - size * 0.31),
        (center + size * 0.31, center),
        (center, center + size * 0.31),
        (center - size * 0.31, center),
    ):
        draw.ellipse((x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius), fill=255)


def _draw_truntum_masks(fill: Image.Image, accent: Image.Image) -> None:
    size = fill.width
    center = size / 2
    points: list[tuple[float, float]] = []
    for index in range(16):
        radius = size * (0.30 if index % 2 == 0 else 0.13)
        angle = -math.pi / 2 + math.tau * index / 16
        points.append(
            (
                center + math.cos(angle) * radius,
                center + math.sin(angle) * radius,
            )
        )
    ImageDraw.Draw(fill).polygon(points, fill=255)

    draw = ImageDraw.Draw(accent)
    center_radius = size * 0.045
    draw.ellipse(
        (
            center - center_radius,
            center - center_radius,
            center + center_radius,
            center + center_radius,
        ),
        fill=255,
    )
    satellite_radius = size * 0.016
    for index in range(8):
        angle = math.tau * index / 8
        x = center + math.cos(angle) * size * 0.37
        y = center + math.sin(angle) * size * 0.37
        draw.ellipse(
            (
                x - satellite_radius,
                y - satellite_radius,
                x + satellite_radius,
                y + satellite_radius,
            ),
            fill=255,
        )


def _draw_ceplok_masks(fill: Image.Image, accent: Image.Image) -> None:
    size = fill.width
    center = size / 2
    for index in range(8):
        angle = 45 * index
        radians = math.radians(angle)
        petal_center_x = center + math.cos(radians) * size * 0.17
        petal_center_y = center + math.sin(radians) * size * 0.17
        petal = _rotated_ellipse(
            size,
            petal_center_x,
            petal_center_y,
            size * 0.17,
            size * 0.36,
            angle + 90,
        )
        fill.paste(ImageChops.lighter(fill, petal))

    draw = ImageDraw.Draw(accent)
    center_radius = size * 0.085
    draw.ellipse(
        (
            center - center_radius,
            center - center_radius,
            center + center_radius,
            center + center_radius,
        ),
        fill=255,
    )
    for index in range(4):
        angle = math.pi / 4 + math.pi / 2 * index
        x = center + math.cos(angle) * size * 0.36
        y = center + math.sin(angle) * size * 0.36
        radius = size * 0.034
        draw.rectangle((x - radius, y - radius, x + radius, y + radius), fill=255)


def _draw_lereng_masks(fill: Image.Image, accent: Image.Image) -> None:
    size = fill.width
    draw_fill = ImageDraw.Draw(fill)
    band_width = max(8, round(size * 0.13))
    for offset in (-0.52, -0.17, 0.18, 0.53):
        start_x = size * offset
        draw_fill.line(
            (start_x, size * 0.98, start_x + size * 0.92, size * 0.06),
            fill=255,
            width=band_width,
        )

    draw = ImageDraw.Draw(accent)
    line_width = max(3, round(size * 0.014))
    for offset in (-0.36, -0.01, 0.34):
        start_x = size * offset
        draw.arc(
            (
                start_x + size * 0.30,
                size * 0.26,
                start_x + size * 0.58,
                size * 0.54,
            ),
            start=205,
            end=515,
            fill=255,
            width=line_width,
        )
        x = start_x + size * 0.57
        y = size * 0.27
        radius = size * 0.026
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)


def _rotated_ellipse(
    size: int,
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    angle: float,
) -> Image.Image:
    layer = Image.new("L", (size, size), 0)
    ImageDraw.Draw(layer).ellipse(
        (
            center_x - width / 2,
            center_y - height / 2,
            center_x + width / 2,
            center_y + height / 2,
        ),
        fill=255,
    )
    return layer.rotate(angle, resample=Image.Resampling.BICUBIC, center=(center_x, center_y))


def _iterated_morphology(image: Image.Image, radius: int, factory: type) -> Image.Image:
    """Terapkan Max/MinFilter(2r+1) sebagai r iterasi kernel 3x3.

    Ekuivalen eksak untuk structuring element persegi, tetapi jauh lebih cepat
    daripada satu rank filter besar (biaya per piksel turun dari O((2r+1)^2)
    menjadi O(9r))."""
    for _ in range(max(0, radius)):
        image = image.filter(factory(3))
    return image


def _outline_from_mask(mask: Image.Image, width: int) -> Image.Image:
    expanded = _iterated_morphology(mask, width, ImageFilter.MaxFilter)
    contracted = _iterated_morphology(mask, width, ImageFilter.MinFilter)
    return ImageChops.subtract(expanded, contracted)


def _validate_motif_type(value: str) -> str:
    if value not in MOTIF_TYPES:
        raise MotifError(f"Motif pokok tidak didukung: {value!r}.")
    return value


def _validate_color(value: str, label: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise MotifError(f"{label} harus berupa warna CSS yang valid.")
    try:
        rgb = ImageColor.getrgb(value)
    except (TypeError, ValueError) as exc:
        raise MotifError(f"{label} tidak valid.") from exc
    return rgb[:3]


__all__ = [
    "DEFAULT_MOTIF_ISEN",
    "MASTER_MOTIF_SIZE",
    "MAX_MOTIF_SIZE",
    "MIN_MOTIF_SIZE",
    "MOTIF_LABELS",
    "MOTIF_TYPES",
    "MotifError",
    "motif_description",
    "render_motif_cap",
    "validate_motif_size",
]
