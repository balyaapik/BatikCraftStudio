"""Output-mode layer for BatikBrew SDXL generation.

Pattern mode keeps the notebook-compatible full seamless composition. Ornament mode
asks SDXL for one isolated Batik ornament, disables tiling, and removes every
border-connected studio background region before the result reaches the canvas.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, replace
from io import BytesIO

from PIL import Image, ImageFilter, ImageStat

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
            f"{options.prompt}, exactly one single isolated Indonesian Batik ornament, "
            "one centered subject only, complete ornamental silhouette, hand-drawn canting "
            "contour, internal isen-isen, large clean empty margin on every side, pure flat "
            "white studio background, background must contain no motif, no texture, no shadow, "
            "no floor, no repeat, no tile, no fabric sheet, no all-over pattern, no border frame"
        )
        ornament_negative = (
            f"{options.negative_prompt}, seamless repeat, tiled pattern, wallpaper, textile sheet, "
            "multiple motifs, motif grid, border, frame, scenery, full background illustration, "
            "background ornament, background pattern, textured background, gradient background, "
            "drop shadow, cast shadow, floor shadow, pedestal, vignette, cropped ornament, "
            "touching image edge"
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
    hard_alpha = alpha.point(lambda value: 255 if value >= 20 else 0)
    bbox = hard_alpha.getbbox()
    if bbox is None:
        raise BatificationError(
            "Ornamen tunggal tidak dapat dipisahkan dari background. Coba seed atau prompt lain."
        )

    cropped = rgba.crop(bbox)
    cropped_alpha = alpha.crop(bbox)
    cropped.putalpha(cropped_alpha)

    padding = max(12, round(min(rgba.size) * 0.04))
    isolated = Image.new(
        "RGBA",
        (cropped.width + padding * 2, cropped.height + padding * 2),
        (0, 0, 0, 0),
    )
    isolated.alpha_composite(cropped, (padding, padding))

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
            "background_removal_method": "adaptive-border-connected-segmentation-v2",
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
    """Return alpha for one object while deleting border-connected generated backgrounds.

    SDXL often produces an off-white gradient, paper texture, vignette, or soft shadow even
    when a plain background is requested. Comparing every pixel with one average corner color
    leaves those regions visible. This implementation models the background as a bilinear plane
    from all four corners and flood-fills only pixels connected to the image border.
    """

    rgb = image.convert("RGB")
    width, height = rgb.size
    corners = _corner_colours(rgb)
    distances = _background_distance_map(rgb, corners)
    border_distances = _border_values(distances, width, height)
    baseline = _percentile(border_distances, 0.90)
    initial_threshold = max(28, min(72, baseline + 16))

    chosen: Image.Image | None = None
    chosen_coverage = 1.0
    for threshold in (
        initial_threshold,
        min(92, initial_threshold + 14),
        min(112, initial_threshold + 28),
    ):
        background = _border_connected_background(distances, width, height, threshold)
        candidate = Image.new("L", (width, height), 0)
        candidate.putdata([255 if not value else 0 for value in background])
        candidate = _keep_ornament_components(candidate)
        coverage = _mask_coverage(candidate)
        if 0.012 <= coverage <= 0.78:
            chosen = candidate
            chosen_coverage = coverage
        if 0.025 <= coverage <= 0.62:
            break

    if chosen is None:
        chosen = _fallback_center_mask(rgb)
        chosen_coverage = _mask_coverage(chosen)

    if chosen_coverage > 0.84:
        chosen = _fallback_center_mask(rgb)

    # Erode one pixel to remove colour fringe, then feather only the true ornament edge.
    alpha = chosen.filter(ImageFilter.MinFilter(3))
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.8))
    return alpha.point(lambda value: 0 if value < 18 else value)


def _corner_colours(image: Image.Image) -> tuple[tuple[int, int, int], ...]:
    width, height = image.size
    radius = max(6, round(min(width, height) * 0.055))
    boxes = (
        (0, 0, radius, radius),
        (width - radius, 0, width, radius),
        (0, height - radius, radius, height),
        (width - radius, height - radius, width, height),
    )
    return tuple(
        tuple(int(round(value)) for value in ImageStat.Stat(image.crop(box)).median[:3])
        for box in boxes
    )


def _background_distance_map(
    image: Image.Image,
    corners: tuple[tuple[int, int, int], ...],
) -> list[int]:
    width, height = image.size
    pixels = image.load()
    top_left, top_right, bottom_left, bottom_right = corners
    values: list[int] = []
    x_denominator = max(1, width - 1)
    y_denominator = max(1, height - 1)

    for y in range(height):
        ty = y / y_denominator
        for x in range(width):
            tx = x / x_denominator
            expected = []
            for channel in range(3):
                top = top_left[channel] * (1 - tx) + top_right[channel] * tx
                bottom = bottom_left[channel] * (1 - tx) + bottom_right[channel] * tx
                expected.append(top * (1 - ty) + bottom * ty)
            pixel = pixels[x, y]
            distance = math.sqrt(
                sum((float(pixel[channel]) - expected[channel]) ** 2 for channel in range(3))
            )
            values.append(min(255, int(round(distance))))
    return values


def _border_values(values: list[int], width: int, height: int) -> list[int]:
    indexes = set(range(width))
    indexes.update((height - 1) * width + x for x in range(width))
    indexes.update(y * width for y in range(height))
    indexes.update(y * width + width - 1 for y in range(height))
    return [values[index] for index in indexes]


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _border_connected_background(
    distances: list[int],
    width: int,
    height: int,
    threshold: int,
) -> bytearray:
    background = bytearray(width * height)
    pending: deque[int] = deque()

    def add(index: int) -> None:
        if not background[index] and distances[index] <= threshold:
            background[index] = 1
            pending.append(index)

    for x in range(width):
        add(x)
        add((height - 1) * width + x)
    for y in range(height):
        add(y * width)
        add(y * width + width - 1)

    while pending:
        index = pending.popleft()
        x = index % width
        y = index // width
        for offset_x, offset_y in (
            (-1, -1),
            (0, -1),
            (1, -1),
            (-1, 0),
            (1, 0),
            (-1, 1),
            (0, 1),
            (1, 1),
        ):
            neighbour_x = x + offset_x
            neighbour_y = y + offset_y
            if not (0 <= neighbour_x < width and 0 <= neighbour_y < height):
                continue
            neighbour = neighbour_y * width + neighbour_x
            add(neighbour)
    return background


def _keep_ornament_components(mask: Image.Image) -> Image.Image:
    width, height = mask.size
    values = list(mask.getdata())
    visited = bytearray(width * height)
    components: list[tuple[list[int], tuple[int, int, int, int]]] = []

    for start, value in enumerate(values):
        if value == 0 or visited[start]:
            continue
        visited[start] = 1
        pending = deque([start])
        indexes: list[int] = []
        min_x = width
        min_y = height
        max_x = 0
        max_y = 0
        while pending:
            index = pending.popleft()
            indexes.append(index)
            x = index % width
            y = index // width
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            for neighbour in (
                index - 1 if x > 0 else -1,
                index + 1 if x + 1 < width else -1,
                index - width if y > 0 else -1,
                index + width if y + 1 < height else -1,
            ):
                if neighbour >= 0 and values[neighbour] and not visited[neighbour]:
                    visited[neighbour] = 1
                    pending.append(neighbour)
        components.append((indexes, (min_x, min_y, max_x + 1, max_y + 1)))

    if not components:
        return mask
    components.sort(key=lambda item: len(item[0]), reverse=True)
    largest_indexes, largest_bbox = components[0]
    keep = bytearray(width * height)
    minimum = max(18, round(len(largest_indexes) * 0.018))
    margin = max(8, round(min(width, height) * 0.12))
    expanded = (
        max(0, largest_bbox[0] - margin),
        max(0, largest_bbox[1] - margin),
        min(width, largest_bbox[2] + margin),
        min(height, largest_bbox[3] + margin),
    )

    for indexes, bbox in components:
        if len(indexes) < minimum or not _bbox_intersects(bbox, expanded):
            continue
        for index in indexes:
            keep[index] = 255

    cleaned = Image.new("L", (width, height), 0)
    cleaned.putdata(keep)
    return cleaned


def _bbox_intersects(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> bool:
    return not (
        first[2] <= second[0]
        or first[0] >= second[2]
        or first[3] <= second[1]
        or first[1] >= second[3]
    )


def _mask_coverage(mask: Image.Image) -> float:
    histogram = mask.histogram()
    foreground = sum(histogram[1:])
    return foreground / max(1, mask.width * mask.height)


def _fallback_center_mask(image: Image.Image) -> Image.Image:
    """Conservative fallback that never returns the complete rectangular background."""

    width, height = image.size
    corners = _corner_colours(image)
    distances = _background_distance_map(image, corners)
    threshold = max(48, _percentile(_border_values(distances, width, height), 0.95) + 24)
    mask = Image.new("L", (width, height), 0)
    mask.putdata([255 if distance > threshold else 0 for distance in distances])
    return _keep_ornament_components(mask)


__all__ = [
    "BatikBrewModeGenerationOptions",
    "BatikBrewModeGenerationProvider",
    "OUTPUT_MODE_ORNAMENT",
    "OUTPUT_MODE_PATTERN",
]
