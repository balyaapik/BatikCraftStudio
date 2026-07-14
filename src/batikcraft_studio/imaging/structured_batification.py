"""Structured, non-destructive Batik rendering foundations.

The local provider is intentionally deterministic and dependency-light. It implements the
same component contract that a future AI provider will use: one rendered component plus an
optional separate isen/filler component. Source objects are never flattened or destroyed.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import StrEnum
from io import BytesIO
from types import MappingProxyType
from typing import Any, Protocol

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageOps

from batikcraft_studio.domain import Layer, LayerKind, LayerObject, ObjectKind, Transform
from batikcraft_studio.imaging.shape import ShapeError, render_shape_image


class BatificationError(RuntimeError):
    """Raised when a structured Batik render cannot be produced."""


class BatificationStyle(StrEnum):
    """Initial style presets shared by local and future AI providers."""

    CLASSIC = "classic"
    PESISIR = "pesisir"
    INDIGO = "indigo"
    MODERN = "modern"
    GEOMETRIC = "geometric"


@dataclass(frozen=True, slots=True)
class BatificationRequest:
    """Serializable settings for one structured Batik generation."""

    style: BatificationStyle = BatificationStyle.CLASSIC
    strength: float = 0.72
    isen_density: float = 0.48
    preserve_palette: bool = False
    primary_color: str = "#4E2A1E"
    secondary_color: str = "#D9A566"
    seed: int = 2026
    add_filler: bool = True
    prompt: str = ""

    def __post_init__(self) -> None:
        try:
            style = BatificationStyle(self.style)
        except (TypeError, ValueError) as exc:
            raise BatificationError(f"Unsupported Batik style: {self.style!r}.") from exc
        strength = _unit(self.strength, "strength")
        density = _unit(self.isen_density, "isen_density")
        primary = _hex_color(self.primary_color, "primary_color")
        secondary = _hex_color(self.secondary_color, "secondary_color")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise BatificationError("seed must be an integer.")
        if not isinstance(self.preserve_palette, bool) or not isinstance(self.add_filler, bool):
            raise BatificationError("Boolean Batification settings are invalid.")
        prompt = str(self.prompt).strip()
        if len(prompt) > 1_000:
            raise BatificationError("prompt must contain at most 1000 characters.")
        object.__setattr__(self, "style", style)
        object.__setattr__(self, "strength", strength)
        object.__setattr__(self, "isen_density", density)
        object.__setattr__(self, "primary_color", primary)
        object.__setattr__(self, "secondary_color", secondary)
        object.__setattr__(self, "prompt", prompt)

    def to_properties(self) -> dict[str, Any]:
        """Return JSON-safe generation settings for project persistence."""

        return {
            "style": self.style.value,
            "strength": self.strength,
            "isen_density": self.isen_density,
            "preserve_palette": self.preserve_palette,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "seed": self.seed,
            "add_filler": self.add_filler,
            "prompt": self.prompt,
        }


@dataclass(frozen=True, slots=True)
class BatificationRender:
    """One rendered component and an optional separately editable filler component."""

    content: bytes
    width: int
    height: int
    provider_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    filler_content: bytes | None = None

    def __post_init__(self) -> None:
        if not self.content:
            raise BatificationError("Rendered Batik component is empty.")
        if self.width < 1 or self.height < 1:
            raise BatificationError("Rendered Batik dimensions must be positive.")
        if not str(self.provider_id).strip():
            raise BatificationError("provider_id must not be blank.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class StructuredBatificationProvider(Protocol):
    """Provider contract implemented later by local, Kaggle, or remote AI backends."""

    provider_id: str

    def render(
        self,
        source_content: bytes,
        request: BatificationRequest,
    ) -> BatificationRender:
        """Render one source component without flattening neighboring objects."""


class LocalStructuredBatificationProvider:
    """Deterministic local foundation renderer used before the final AI backend exists."""

    provider_id = "local-structured-foundation-v1"

    def render(
        self,
        source_content: bytes,
        request: BatificationRequest,
    ) -> BatificationRender:
        source = _open_rgba(source_content)
        alpha = source.getchannel("A")
        if alpha.getbbox() is None:
            raise BatificationError("Source object is fully transparent.")

        base = _stylized_base(source, request)
        linework = _batik_linework(source, request)
        patterned = Image.alpha_composite(base, linework)
        pattern = _isen_pattern(source.size, alpha, request)
        patterned = Image.alpha_composite(patterned, pattern)

        output = BytesIO()
        patterned.save(output, format="PNG", optimize=True)
        filler_content: bytes | None = None
        if request.add_filler:
            filler = _filler_pattern(source.size, alpha, request)
            filler_output = BytesIO()
            filler.save(filler_output, format="PNG", optimize=True)
            filler_content = filler_output.getvalue()

        return BatificationRender(
            content=output.getvalue(),
            width=source.width,
            height=source.height,
            provider_id=self.provider_id,
            metadata={
                "foundation_renderer": True,
                "style": request.style.value,
                "seed": request.seed,
            },
            filler_content=filler_content,
        )


def renderable_source_content(
    item: LayerObject,
    assets: dict[str, bytes] | Any,
) -> bytes:
    """Return an untransformed transparent source PNG for one editable object."""

    if item.kind is ObjectKind.ERASER_STROKE:
        raise BatificationError("Eraser strokes cannot be Batik-rendered independently.")
    if item.kind is ObjectKind.SHAPE:
        legacy_shape = Layer(
            name=item.name,
            kind=LayerKind.SHAPE,
            transform=Transform(),
            properties={
                **dict(item.properties),
                "pixel_width": item.bounds.width,
                "pixel_height": item.bounds.height,
            },
        )
        try:
            image = render_shape_image(
                legacy_shape,
                max(1, round(item.bounds.width)),
                max(1, round(item.bounds.height)),
            )
        except ShapeError as exc:
            raise BatificationError(f"Shape {item.name!r} is invalid.") from exc
        output = BytesIO()
        image.convert("RGBA").save(output, format="PNG", optimize=True)
        return output.getvalue()

    if item.asset_ref is None:
        raise BatificationError(f"Object {item.name!r} has no renderable source asset.")
    try:
        content = assets[item.asset_ref]
    except KeyError as exc:
        raise BatificationError(
            f"Source asset for object {item.name!r} is unavailable."
        ) from exc
    image = _open_rgba(content)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _stylized_base(source: Image.Image, request: BatificationRequest) -> Image.Image:
    alpha = source.getchannel("A")
    if request.preserve_palette:
        reduced = ImageOps.posterize(source.convert("RGB"), bits=4).convert("RGBA")
        reduced.putalpha(alpha)
        return Image.blend(source, reduced, request.strength)

    gray = ImageOps.autocontrast(source.convert("L"))
    primary = ImageColor.getrgb(request.primary_color)
    secondary = ImageColor.getrgb(request.secondary_color)
    palette = ImageOps.colorize(gray, black=primary, white=secondary).convert("RGBA")
    palette.putalpha(alpha)
    return Image.blend(source, palette, request.strength)


def _batik_linework(source: Image.Image, request: BatificationRequest) -> Image.Image:
    gray = source.convert("L")
    edges = ImageOps.autocontrast(gray.filter(ImageFilter.FIND_EDGES))
    threshold = round(185 - request.strength * 70)
    mask = edges.point(lambda value: 255 if value >= threshold else 0)
    mask = mask.filter(ImageFilter.MaxFilter(3))
    mask = ImageChops.multiply(mask, source.getchannel("A"))
    line = Image.new("RGBA", source.size, (*ImageColor.getrgb(request.primary_color), 0))
    line.putalpha(mask)
    return line


def _isen_pattern(
    size: tuple[int, int],
    alpha: Image.Image,
    request: BatificationRequest,
) -> Image.Image:
    width, height = size
    output = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(output)
    rng = random.Random(request.seed)
    spacing = max(7, round(30 - request.isen_density * 20))
    radius = max(1, round(spacing * (0.08 + request.strength * 0.05)))
    color = (*ImageColor.getrgb(request.primary_color), round(70 + 95 * request.strength))
    offset = rng.randrange(spacing)
    for y in range(offset, height, spacing):
        row_offset = (y // spacing % 2) * (spacing // 2)
        for x in range(row_offset, width, spacing):
            jitter_x = rng.randint(-max(1, spacing // 8), max(1, spacing // 8))
            jitter_y = rng.randint(-max(1, spacing // 8), max(1, spacing // 8))
            cx, cy = x + jitter_x, y + jitter_y
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color)
    output.putalpha(ImageChops.multiply(output.getchannel("A"), alpha))
    return output


def _filler_pattern(
    size: tuple[int, int],
    alpha: Image.Image,
    request: BatificationRequest,
) -> Image.Image:
    width, height = size
    output = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(output)
    spacing = max(12, round(42 - request.isen_density * 25))
    color = (*ImageColor.getrgb(request.secondary_color), round(70 + request.strength * 85))
    diagonal = width + height
    for value in range(-height, diagonal, spacing):
        draw.line(
            (value, 0, value + height, height),
            fill=color,
            width=max(1, round(1 + request.strength * 2)),
        )
    clipped_alpha = ImageChops.multiply(output.getchannel("A"), alpha)
    softened = clipped_alpha.filter(ImageFilter.GaussianBlur(radius=0.35))
    output.putalpha(softened)
    return output


def _open_rgba(content: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            return source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise BatificationError("Source image cannot be decoded.") from exc


def _unit(value: float, label: str) -> float:
    if isinstance(value, bool):
        raise BatificationError(f"{label} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BatificationError(f"{label} must be numeric.") from exc
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise BatificationError(f"{label} must be between 0 and 1.")
    return number


def _hex_color(value: str, label: str) -> str:
    text = str(value).strip().upper()
    try:
        ImageColor.getrgb(text)
    except ValueError as exc:
        raise BatificationError(f"{label} must be a valid color.") from exc
    if len(text) != 7 or not text.startswith("#"):
        raise BatificationError(f"{label} must use #RRGGBB.")
    return text


__all__ = [
    "BatificationError",
    "BatificationRender",
    "BatificationRequest",
    "BatificationStyle",
    "LocalStructuredBatificationProvider",
    "StructuredBatificationProvider",
    "renderable_source_content",
]
