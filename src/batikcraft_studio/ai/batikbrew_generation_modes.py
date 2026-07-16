"""Output-mode layer for BatikBrew SDXL generation.

Pattern mode keeps the notebook-compatible full seamless composition. Ornament mode
asks SDXL for one isolated Batik ornament, disables tiling, and converts the plain
studio background into alpha so the result behaves like a normal canvas object.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from io import BytesIO

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat

from batikcraft_studio.ai.batikbrew_generation import (
    BatikBrewGenerationOptions,
    BatikBrewSDXLGenerationProvider,
)
from batikcraft_studio.ai.pretrained_batification import (
    PretrainedAIBatificationOptions,
    PretrainedAIBatificationResult,
)
from batikcraft_studio.imaging.structured_batification import BatificationError

OUTPUT_MODE_ORNAMENT = "ornament"
OUTPUT_MODE_PATTERN = "pattern"
_OUTPUT_MODES = {OUTPUT_MODE_ORNAMENT, OUTPUT_MODE_PATTERN}


@dataclass(frozen=True, slots=True)
class BatikBrewModeGenerationOptions(BatikBrewGenerationOptions):
    """BatikBrew controls with an explicit single-ornament or pattern mode."""

    output_mode: str = OUTPUT_MODE_PATTERN

    def __post_init__(self) -> None:
        super().__post_init__()
        mode = str(self.output_mode).strip().casefold()
        if mode not in _OUTPUT_MODES:
            raise BatificationError("Mode hasil harus 'ornament' atau 'pattern'.")
        object.__setattr__(self, "output_mode", mode)
        if mode == OUTPUT_MODE_ORNAMENT:
            object.__setattr__(self, "tileable", False)

    def to_properties(self) -> dict[str, object]:
        properties = super().to_properties()
        properties.update(
            {
                "output_mode": self.output_mode,
                "clipboard_copyable": True,
                "transparent_background": self.output_mode == OUTPUT_MODE_ORNAMENT,
            }
        )
        return properties


class BatikBrewModeGenerationProvider(BatikBrewSDXLGenerationProvider):
    """Generate either one isolated ornament or a full repeating pattern."""

    def render_variations(
        self,
        source_content: bytes,
        motif_content: bytes,
        options: PretrainedAIBatificationOptions | None = None,
    ) -> tuple[PretrainedAIBatificationResult, ...]:
        if not isinstance(options, BatikBrewModeGenerationOptions):
            raise BatificationError("Pilih mode Ornamen Tunggal atau Pola sebelum generate.")

        if options.output_mode == OUTPUT_MODE_PATTERN:
            results = super().render_variations(source_content, motif_content, options)
            return tuple(_with_mode_metadata(item, OUTPUT_MODE_PATTERN) for item in results)

        ornament_direction = (
            f"{options.prompt}, one single isolated Indonesian Batik ornament, centered subject, "
            "complete ornamental silhouette, hand-drawn canting contour, internal isen-isen, "
            "generous empty margin, plain uniform light background, no repeat, no tile, no fabric "
            "sheet, no all-over pattern, no border frame"
        )
        ornament_negative = (
            f"{options.negative_prompt}, seamless repeat, tiled pattern, wallpaper, textile sheet, "
            "multiple motifs, motif grid, border, frame, scenery, full background illustration, "
            "cropped ornament, touching image edge"
        )
        ornament_options = replace(
            options,
            prompt=ornament_direction,
            negative_prompt=ornament_negative,
            tileable=False,
        )
        raw_results = super().render_variations(
            source_content,
            motif_content,
            ornament_options,
        )
        return tuple(_isolate_ornament(item) for item in raw_results)


def _with_mode_metadata(
    result: PretrainedAIBatificationResult,
    mode: str,
) -> PretrainedAIBatificationResult:
    metadata = dict(result.metadata)
    metadata.update(
        {
            "output_mode": mode,
            "single_ornament": mode == OUTPUT_MODE_ORNAMENT,
            "full_pattern": mode == OUTPUT_MODE_PATTERN,
            "clipboard_copyable": True,
        }
    )
    return PretrainedAIBatificationResult(
        content=result.content,
        width=result.width,
        height=result.height,
        provider_id=f"{result.provider_id}+{mode}",
        metadata=metadata,
    )


def _isolate_ornament(result: PretrainedAIBatificationResult) -> PretrainedAIBatificationResult:
    with Image.open(BytesIO(result.content)) as source:
        rgba = source.convert("RGBA")
    alpha = _background_alpha(rgba)
    bbox = alpha.getbbox()
    if bbox is None:
        isolated = rgba
    else:
        padded = _padded_bbox(bbox, rgba.size, padding=max(12, round(min(rgba.size) * 0.04)))
        isolated = rgba.crop(padded)
        cropped_alpha = alpha.crop(padded)
        isolated.putalpha(cropped_alpha)

    encoded = BytesIO()
    isolated.save(encoded, format="PNG", optimize=True)
    metadata = dict(result.metadata)
    metadata.update(
        {
            "output_mode": OUTPUT_MODE_ORNAMENT,
            "single_ornament": True,
            "full_pattern": False,
            "tileable": False,
            "transparent_background": True,
            "background_removed": True,
            "clipboard_copyable": True,
        }
    )
    return PretrainedAIBatificationResult(
        content=encoded.getvalue(),
        width=isolated.width,
        height=isolated.height,
        provider_id=f"{result.provider_id}+ornament",
        metadata=metadata,
    )


def _background_alpha(image: Image.Image) -> Image.Image:
    """Estimate a plain SDXL studio background from the image corners."""

    rgb = image.convert("RGB")
    width, height = rgb.size
    radius = max(3, round(min(width, height) * 0.03))
    corners = (
        rgb.crop((0, 0, radius, radius)),
        rgb.crop((width - radius, 0, width, radius)),
        rgb.crop((0, height - radius, radius, height)),
        rgb.crop((width - radius, height - radius, width, height)),
    )
    samples = [ImageStat.Stat(corner).median[:3] for corner in corners]
    background = tuple(round(sum(sample[channel] for sample in samples) / len(samples)) for channel in range(3))
    background_image = Image.new("RGB", rgb.size, background)
    difference = ImageChops.difference(rgb, background_image).convert("L")
    difference = ImageOps.autocontrast(difference)
    alpha = difference.point(lambda value: 0 if value < 22 else min(255, round((value - 22) * 2.7)))
    alpha = alpha.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(1.1))
    alpha = alpha.point(lambda value: 0 if value < 18 else value)
    return alpha


def _padded_bbox(
    bbox: tuple[int, int, int, int],
    size: tuple[int, int],
    *,
    padding: int,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    width, height = size
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


__all__ = [
    "BatikBrewModeGenerationOptions",
    "BatikBrewModeGenerationProvider",
    "OUTPUT_MODE_ORNAMENT",
    "OUTPUT_MODE_PATTERN",
]
