"""Clean noisy raster outlines into smooth transparent line assets."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageChops, ImageColor, ImageFilter, ImageOps

from .raster import RasterImageError, normalize_raster_image

_SOURCE_MODES = {"auto", "dark", "alpha"}


class OutlineCleanupError(ValueError):
    """Raised when an image cannot produce a usable cleaned outline."""


@dataclass(frozen=True, slots=True)
class OutlineCleanupOptions:
    """Settings for deterministic, dependency-free outline cleanup."""

    threshold: int = 96
    speckle_area: int = 24
    smooth_radius: float = 0.8
    close_gaps: int = 1
    thin_lines: int = 0
    outline_only: bool = False
    source_mode: str = "auto"
    invert: bool = False
    line_color: str = "#1C1714"

    def __post_init__(self) -> None:
        if isinstance(self.threshold, bool) or not 0 <= self.threshold <= 255:
            raise OutlineCleanupError("Ambang garis harus berada pada rentang 0–255.")
        if isinstance(self.speckle_area, bool) or not 0 <= self.speckle_area <= 20_000:
            raise OutlineCleanupError("Ukuran bercak harus berada pada rentang 0–20.000 piksel.")
        if not 0.0 <= float(self.smooth_radius) <= 8.0:
            raise OutlineCleanupError("Penghalusan tepi harus berada pada rentang 0–8.")
        if isinstance(self.close_gaps, bool) or not 0 <= self.close_gaps <= 6:
            raise OutlineCleanupError("Penutupan celah harus berada pada rentang 0–6.")
        if isinstance(self.thin_lines, bool) or not 0 <= self.thin_lines <= 6:
            raise OutlineCleanupError("Penipisan garis harus berada pada rentang 0–6.")
        if self.source_mode not in _SOURCE_MODES:
            raise OutlineCleanupError("Mode sumber outline tidak didukung.")
        try:
            ImageColor.getrgb(self.line_color)
        except ValueError as exc:
            raise OutlineCleanupError("Warna garis tidak valid.") from exc

    def to_properties(self) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "speckle_area": self.speckle_area,
            "smooth_radius": round(float(self.smooth_radius), 3),
            "close_gaps": self.close_gaps,
            "thin_lines": self.thin_lines,
            "outline_only": self.outline_only,
            "source_mode": self.source_mode,
            "invert": self.invert,
            "line_color": self.line_color.upper(),
        }


@dataclass(frozen=True, slots=True)
class OutlineCleanupResult:
    """One transparent PNG candidate plus cleanup diagnostics."""

    content: bytes
    width: int
    height: int
    removed_components: int
    removed_pixels: int
    input_coverage: float
    output_coverage: float
    resolved_source_mode: str


def clean_outline(
    content: bytes | bytearray | memoryview,
    options: OutlineCleanupOptions | None = None,
) -> OutlineCleanupResult:
    """Return a smooth transparent line asset while preserving the original dimensions."""

    settings = options or OutlineCleanupOptions()
    try:
        normalized = normalize_raster_image(content)
    except RasterImageError as exc:
        raise OutlineCleanupError(str(exc)) from exc

    with Image.open(BytesIO(normalized.content)) as source:
        source.load()
        rgba = source.convert("RGBA")

    strength, resolved_mode = _ink_strength(rgba, settings.source_mode)
    if settings.invert:
        strength = ImageOps.invert(strength)
    binary = strength.point(lambda value: 255 if value >= settings.threshold else 0, mode="L")
    input_coverage = _coverage(binary)
    if input_coverage <= 0.0:
        raise OutlineCleanupError(
            "Tidak ada garis yang terdeteksi. Turunkan ambang atau ubah mode sumber."
        )

    if settings.close_gaps:
        size = settings.close_gaps * 2 + 1
        binary = binary.filter(ImageFilter.MaxFilter(size))
        binary = binary.filter(ImageFilter.MinFilter(size))

    binary, removed_components, removed_pixels = _remove_small_components(
        binary,
        settings.speckle_area,
    )

    if settings.outline_only:
        radius = max(1, settings.close_gaps or 1)
        size = radius * 2 + 1
        dilated = binary.filter(ImageFilter.MaxFilter(size))
        eroded = binary.filter(ImageFilter.MinFilter(size))
        contour = ImageChops.subtract(dilated, eroded)
        if _coverage(contour) > 0.0:
            binary = contour

    for _index in range(settings.thin_lines):
        thinned = binary.filter(ImageFilter.MinFilter(3))
        if _coverage(thinned) <= 0.0:
            break
        binary = thinned

    alpha = binary
    if settings.smooth_radius > 0:
        alpha = binary.filter(ImageFilter.GaussianBlur(float(settings.smooth_radius)))
        alpha = alpha.point(lambda value: 0 if value < 8 else value, mode="L")

    output_coverage = _coverage(alpha)
    if output_coverage <= 0.0:
        raise OutlineCleanupError(
            "Semua garis hilang setelah pembersihan. Kurangi penipisan atau ukuran bercak."
        )

    red, green, blue = ImageColor.getrgb(settings.line_color)
    output = Image.new("RGBA", rgba.size, (red, green, blue, 0))
    output.putalpha(alpha)
    encoded = BytesIO()
    output.save(encoded, format="PNG", optimize=True)

    return OutlineCleanupResult(
        content=encoded.getvalue(),
        width=output.width,
        height=output.height,
        removed_components=removed_components,
        removed_pixels=removed_pixels,
        input_coverage=input_coverage,
        output_coverage=output_coverage,
        resolved_source_mode=resolved_mode,
    )


def _ink_strength(image: Image.Image, source_mode: str) -> tuple[Image.Image, str]:
    alpha = image.getchannel("A")
    darkness = ImageOps.invert(ImageOps.grayscale(image))
    if source_mode == "alpha":
        return alpha, "alpha"
    if source_mode == "dark":
        return darkness, "dark"

    histogram = alpha.histogram()
    partly_transparent = sum(histogram[:250])
    total = max(1, image.width * image.height)
    if partly_transparent / total >= 0.01:
        return alpha, "alpha"
    return darkness, "dark"


def _coverage(mask: Image.Image) -> float:
    histogram = mask.histogram()
    visible = sum(histogram[1:])
    return visible / max(1, mask.width * mask.height)


def _remove_small_components(
    mask: Image.Image,
    minimum_area: int,
) -> tuple[Image.Image, int, int]:
    if minimum_area <= 0:
        return mask, 0, 0

    width, height = mask.size
    pixels = bytearray(mask.tobytes())
    visited = bytearray(len(pixels))
    removed_components = 0
    removed_pixels = 0

    for start in range(len(pixels)):
        if pixels[start] == 0 or visited[start]:
            continue
        stack = [start]
        small_component: list[int] = []
        component_size = 0

        while stack:
            index = stack.pop()
            if visited[index] or pixels[index] == 0:
                continue
            visited[index] = 1
            component_size += 1
            if component_size <= minimum_area:
                small_component.append(index)

            x = index % width
            y = index // width
            for offset_y in (-1, 0, 1):
                neighbor_y = y + offset_y
                if neighbor_y < 0 or neighbor_y >= height:
                    continue
                row = neighbor_y * width
                for offset_x in (-1, 0, 1):
                    if offset_x == 0 and offset_y == 0:
                        continue
                    neighbor_x = x + offset_x
                    if neighbor_x < 0 or neighbor_x >= width:
                        continue
                    neighbor = row + neighbor_x
                    if pixels[neighbor] and not visited[neighbor]:
                        stack.append(neighbor)

        if component_size <= minimum_area:
            removed_components += 1
            removed_pixels += component_size
            for index in small_component:
                pixels[index] = 0

    return Image.frombytes("L", (width, height), bytes(pixels)), removed_components, removed_pixels


__all__ = [
    "OutlineCleanupError",
    "OutlineCleanupOptions",
    "OutlineCleanupResult",
    "clean_outline",
]
