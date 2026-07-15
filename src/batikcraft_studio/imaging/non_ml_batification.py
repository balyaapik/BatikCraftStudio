"""Deterministic motif-to-object Batification without an ML model.

The source object supplies silhouette, linework, and optional luminance. A second
object supplies the actual Batik motif and palette. The result is a transparent
RGBA object that can be stored like any other editable raster component.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from statistics import median

from PIL import (
    Image,
    ImageChops,
    ImageColor,
    ImageEnhance,
    ImageFilter,
    ImageOps,
    UnidentifiedImageError,
)


class NonMLBatificationError(RuntimeError):
    """Raised when deterministic Batification cannot produce a safe result."""


class NonMLBatificationMode(StrEnum):
    """Ways in which motif information is transferred to the source object."""

    FILL = "fill"
    OUTLINE = "outline"
    FILL_OUTLINE = "fill_outline"


@dataclass(frozen=True, slots=True)
class NonMLBatificationOptions:
    """Serializable options for one local motif-transfer operation."""

    mode: NonMLBatificationMode = NonMLBatificationMode.FILL_OUTLINE
    pattern_scale: float = 0.65
    pattern_rotation: float = 0.0
    pattern_opacity: float = 1.0
    outline_strength: float = 1.0
    outline_width: int = 2
    preserve_shading: float = 0.42
    background_tolerance: int = 24

    def __post_init__(self) -> None:
        try:
            mode = NonMLBatificationMode(self.mode)
        except (TypeError, ValueError) as exc:
            raise NonMLBatificationError(
                f"Unsupported Batification mode: {self.mode!r}."
            ) from exc
        pattern_scale = _finite(self.pattern_scale, "pattern_scale")
        rotation = _finite(self.pattern_rotation, "pattern_rotation")
        opacity = _unit(self.pattern_opacity, "pattern_opacity")
        outline = _unit(self.outline_strength, "outline_strength")
        shading = _unit(self.preserve_shading, "preserve_shading")
        if not 0.08 <= pattern_scale <= 8.0:
            raise NonMLBatificationError("pattern_scale must be between 0.08 and 8.0.")
        if isinstance(self.outline_width, bool) or not 1 <= int(self.outline_width) <= 64:
            raise NonMLBatificationError("outline_width must be between 1 and 64.")
        invalid_tolerance = isinstance(self.background_tolerance, bool) or not (
            1 <= int(self.background_tolerance) <= 128
        )
        if invalid_tolerance:
            raise NonMLBatificationError(
                "background_tolerance must be between 1 and 128."
            )
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "pattern_scale", pattern_scale)
        object.__setattr__(self, "pattern_rotation", rotation % 360.0)
        object.__setattr__(self, "pattern_opacity", opacity)
        object.__setattr__(self, "outline_strength", outline)
        object.__setattr__(self, "outline_width", int(self.outline_width))
        object.__setattr__(self, "preserve_shading", shading)
        object.__setattr__(self, "background_tolerance", int(self.background_tolerance))

    def to_properties(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "pattern_scale": self.pattern_scale,
            "pattern_rotation": self.pattern_rotation,
            "pattern_opacity": self.pattern_opacity,
            "outline_strength": self.outline_strength,
            "outline_width": self.outline_width,
            "preserve_shading": self.preserve_shading,
            "background_tolerance": self.background_tolerance,
        }


@dataclass(frozen=True, slots=True)
class NonMLBatificationResult:
    """Encoded Batification output plus reusable visual metadata."""

    content: bytes
    width: int
    height: int
    palette: tuple[str, ...]
    darkest_color: str
    line_like_source: bool
    mask_coverage: float


def batify_with_motif(
    source_content: bytes,
    motif_content: bytes,
    options: NonMLBatificationOptions | None = None,
) -> NonMLBatificationResult:
    """Transfer a real Batik motif into a source object's alpha/silhouette.

    No model, network access, or learned parameters are used. All operations are
    deterministic Pillow image operations over object-local images.
    """

    settings = options or NonMLBatificationOptions()
    source = _open_rgba(source_content, "source object")
    motif = _open_rgba(motif_content, "Batik motif")
    if source.width * source.height > 40_000_000:
        raise NonMLBatificationError("The source object is too large for local Batification.")

    source_mask = build_object_mask(source, tolerance=settings.background_tolerance)
    bbox = source_mask.getbbox()
    if bbox is None:
        raise NonMLBatificationError("The source object has no visible pixels.")
    coverage = _coverage(source_mask)
    line_like = _is_line_like(source_mask, coverage)

    palette = extract_motif_palette(motif)
    darkest = min(palette, key=_luminance)
    pattern = tile_motif_into_mask(
        motif,
        source_mask,
        pattern_scale=settings.pattern_scale,
        pattern_rotation=settings.pattern_rotation,
        opacity=settings.pattern_opacity,
        fallback_color=palette[-1],
    )
    if settings.preserve_shading > 0:
        pattern = _apply_source_shading(
            pattern,
            source,
            source_mask,
            amount=settings.preserve_shading,
        )

    outline = _build_outline(
        source_mask,
        darkest,
        line_like=line_like,
        width=settings.outline_width,
        strength=settings.outline_strength,
    )
    result = Image.new("RGBA", source.size, (0, 0, 0, 0))
    if settings.mode in {NonMLBatificationMode.FILL, NonMLBatificationMode.FILL_OUTLINE}:
        result.alpha_composite(pattern)
    if settings.mode in {NonMLBatificationMode.OUTLINE, NonMLBatificationMode.FILL_OUTLINE}:
        result.alpha_composite(outline)

    if result.getchannel("A").getbbox() is None:
        raise NonMLBatificationError("Batification produced an empty result.")
    output = BytesIO()
    result.save(output, format="PNG", optimize=True)
    return NonMLBatificationResult(
        content=output.getvalue(),
        width=result.width,
        height=result.height,
        palette=palette,
        darkest_color=darkest,
        line_like_source=line_like,
        mask_coverage=coverage,
    )


def build_object_mask(source: Image.Image, *, tolerance: int = 24) -> Image.Image:
    """Return a soft object mask, preferring alpha and safely handling plain backgrounds."""

    image = source.convert("RGBA")
    alpha = image.getchannel("A")
    extrema = alpha.getextrema()
    if extrema != (255, 255):
        if alpha.getbbox() is None:
            raise NonMLBatificationError("The source object is fully transparent.")
        return alpha

    rgb = image.convert("RGB")
    sample_points = (
        (0, 0),
        (max(0, image.width - 1), 0),
        (0, max(0, image.height - 1)),
        (max(0, image.width - 1), max(0, image.height - 1)),
    )
    samples = [rgb.getpixel(point) for point in sample_points]
    background = tuple(round(median(channel)) for channel in zip(*samples, strict=True))
    difference = ImageChops.difference(rgb, Image.new("RGB", image.size, background))
    red, green, blue = difference.split()
    magnitude = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    hard = magnitude.point(lambda value: 255 if value >= tolerance else 0)
    if hard.getbbox() is None:
        raise NonMLBatificationError(
            "The opaque source cannot be separated from its background safely. "
            "Use a transparent PNG or a simpler background."
        )
    hard = hard.filter(ImageFilter.MaxFilter(3))
    mask = hard.filter(ImageFilter.GaussianBlur(radius=0.65))
    if _coverage(mask) > 0.965:
        raise NonMLBatificationError(
            "The source background is not simple enough to remove safely. "
            "Use a transparent PNG to avoid a rectangular result."
        )
    return mask


def extract_motif_palette(motif: Image.Image, *, colors: int = 6) -> tuple[str, ...]:
    """Extract stable representative colors ordered from dark to light."""

    rgba = motif.convert("RGBA")
    if rgba.getchannel("A").getbbox() is None:
        raise NonMLBatificationError("The Batik motif is fully transparent.")
    flattened = Image.new("RGBA", rgba.size, (245, 239, 226, 255))
    flattened.alpha_composite(rgba)
    sample = flattened.convert("RGB")
    sample.thumbnail((128, 128), Image.Resampling.LANCZOS)
    quantized = sample.quantize(
        colors=max(2, min(12, int(colors))),
        method=Image.Quantize.MEDIANCUT,
    )
    palette_data = quantized.getpalette() or []
    counts = quantized.getcolors(maxcolors=256) or []
    ranked: list[tuple[int, tuple[int, int, int]]] = []
    for count, index in counts:
        offset = int(index) * 3
        if offset + 2 >= len(palette_data):
            continue
        ranked.append((count, tuple(palette_data[offset : offset + 3])))
    if not ranked:
        raise NonMLBatificationError("The Batik motif palette cannot be extracted.")
    ranked.sort(reverse=True, key=lambda item: item[0])
    unique = {color for _count, color in ranked}
    ordered = sorted(unique, key=lambda color: _luminance(_hex(color)))
    return tuple(_hex(color) for color in ordered)


def tile_motif_into_mask(
    motif: Image.Image,
    mask: Image.Image,
    *,
    pattern_scale: float,
    pattern_rotation: float,
    opacity: float,
    fallback_color: str,
) -> Image.Image:
    """Repeat and clip a motif into an object-local alpha mask."""

    rgba = motif.convert("RGBA")
    backdrop = Image.new("RGBA", rgba.size, (*ImageColor.getrgb(fallback_color), 255))
    backdrop.alpha_composite(rgba)
    tile_width = max(8, round(backdrop.width * pattern_scale))
    tile_height = max(8, round(backdrop.height * pattern_scale))
    tile_width = min(max(8, mask.width * 4), tile_width)
    tile_height = min(max(8, mask.height * 4), tile_height)
    tile = backdrop.resize((tile_width, tile_height), Image.Resampling.LANCZOS)
    if pattern_rotation:
        tile = tile.rotate(
            -pattern_rotation,
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )
    tiled = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    for top in range(0, mask.height, max(1, tile.height)):
        for left in range(0, mask.width, max(1, tile.width)):
            tiled.alpha_composite(tile, dest=(left, top))
    alpha = mask
    if opacity < 1.0:
        alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
    tiled.putalpha(ImageChops.multiply(tiled.getchannel("A"), alpha))
    return tiled


def _apply_source_shading(
    pattern: Image.Image,
    source: Image.Image,
    mask: Image.Image,
    *,
    amount: float,
) -> Image.Image:
    gray = ImageOps.autocontrast(source.convert("L"), cutoff=1)
    modulation = gray.point(lambda value: round(155 + value * 100 / 255))
    modulation_rgb = Image.merge("RGB", (modulation, modulation, modulation))
    base_rgb = pattern.convert("RGB")
    shaded_rgb = ImageChops.multiply(base_rgb, modulation_rgb)
    blended = Image.blend(base_rgb, shaded_rgb, amount).convert("RGBA")
    blended.putalpha(ImageChops.multiply(pattern.getchannel("A"), mask))
    return blended


def _build_outline(
    mask: Image.Image,
    color: str,
    *,
    line_like: bool,
    width: int,
    strength: float,
) -> Image.Image:
    if line_like:
        edge = mask
    else:
        radius = max(1, int(width))
        size = radius * 2 + 1
        outer = mask.filter(ImageFilter.MaxFilter(size))
        inner = mask.filter(ImageFilter.MinFilter(size))
        edge = ImageChops.subtract(outer, inner)
    if strength < 1.0:
        edge = ImageEnhance.Brightness(edge).enhance(strength)
    outline = Image.new("RGBA", mask.size, (*ImageColor.getrgb(color), 0))
    outline.putalpha(edge)
    return outline


def _is_line_like(mask: Image.Image, coverage: float) -> bool:
    if coverage <= 0.22:
        return True
    eroded = mask.filter(ImageFilter.MinFilter(5))
    return eroded.getbbox() is None and coverage < 0.50


def _coverage(mask: Image.Image) -> float:
    histogram = mask.histogram()
    weighted = sum(value * count for value, count in enumerate(histogram))
    return weighted / max(1, mask.width * mask.height * 255)


def _open_rgba(content: bytes, label: str) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            return source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise NonMLBatificationError(f"The {label} image cannot be decoded.") from exc


def _hex(color: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*color)


def _luminance(color: str) -> float:
    red, green, blue = ImageColor.getrgb(color)[:3]
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise NonMLBatificationError(f"{label} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise NonMLBatificationError(f"{label} must be numeric.") from exc
    if not math.isfinite(number):
        raise NonMLBatificationError(f"{label} must be finite.")
    return number


def _unit(value: object, label: str) -> float:
    number = _finite(value, label)
    if not 0.0 <= number <= 1.0:
        raise NonMLBatificationError(f"{label} must be between 0 and 1.")
    return number


__all__ = [
    "NonMLBatificationError",
    "NonMLBatificationMode",
    "NonMLBatificationOptions",
    "NonMLBatificationResult",
    "batify_with_motif",
    "build_object_mask",
    "extract_motif_palette",
    "tile_motif_into_mask",
]
