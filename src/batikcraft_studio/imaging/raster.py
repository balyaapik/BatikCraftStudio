"""Raster image validation and normalization for editable layers."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

MAX_RASTER_DIMENSION = 16_384
MAX_RASTER_PIXELS = 64_000_000


class RasterImageError(ValueError):
    """Raised when imported image bytes cannot become a safe raster asset."""


@dataclass(frozen=True, slots=True)
class RasterAsset:
    """Normalized PNG bytes and metadata used by a raster layer."""

    content: bytes
    width: int
    height: int
    source_format: str


def normalize_raster_image(content: bytes | bytearray | memoryview) -> RasterAsset:
    """Validate image bytes and return a deterministic RGBA PNG asset."""

    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise RasterImageError("Image content must be bytes-like.")
    raw = bytes(content)
    if not raw:
        raise RasterImageError("Image content must not be empty.")

    try:
        with Image.open(BytesIO(raw)) as source:
            source_format = (source.format or "UNKNOWN").upper()
            width, height = source.size
            _validate_dimensions(width, height)
            source.load()
            normalized = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise RasterImageError("The selected file is not a readable PNG or JPEG image.") from exc
    except Image.DecompressionBombError as exc:
        raise RasterImageError("The selected image exceeds the safe pixel limit.") from exc

    output = BytesIO()
    normalized.save(output, format="PNG", optimize=True)
    return RasterAsset(
        content=output.getvalue(),
        width=width,
        height=height,
        source_format=source_format,
    )


def _validate_dimensions(width: int, height: int) -> None:
    if width < 1 or height < 1:
        raise RasterImageError("Image dimensions must be positive.")
    if width > MAX_RASTER_DIMENSION or height > MAX_RASTER_DIMENSION:
        raise RasterImageError(
            f"Image dimensions must not exceed {MAX_RASTER_DIMENSION}px per side."
        )
    if width * height > MAX_RASTER_PIXELS:
        raise RasterImageError(
            f"Image must contain at most {MAX_RASTER_PIXELS:,} pixels."
        )
