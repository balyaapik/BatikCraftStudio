"""Portable Batik assets and deterministic hand-drawn raster variation."""

from __future__ import annotations

import base64
import json
import math
import random
from dataclasses import dataclass, field
from io import BytesIO
from types import MappingProxyType
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, UnidentifiedImageError

from batikcraft_studio.imaging.raster import normalize_raster_image

ASSET_FORMAT = "batikcraft-asset"
ASSET_SCHEMA_VERSION = "1.0"
ASSET_CATEGORIES = ("motif-pokok", "isen-isen", "ornamen", "tekstur", "lainnya")


class BatikAssetError(ValueError):
    """Raised when an asset package or humanize request is invalid."""


@dataclass(frozen=True, slots=True)
class EditableBatikAsset:
    """One reusable transparent asset with editable metadata."""

    name: str
    category: str
    content: bytes
    width: int
    height: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name or len(name) > 120:
            raise BatikAssetError("Nama asset harus berisi 1–120 karakter.")
        if self.category not in ASSET_CATEGORIES:
            raise BatikAssetError(f"Kategori asset tidak didukung: {self.category!r}.")
        if not isinstance(self.content, bytes) or not self.content:
            raise BatikAssetError("Asset harus memiliki PNG sumber.")
        if not isinstance(self.width, int) or not isinstance(self.height, int):
            raise BatikAssetError("Ukuran asset harus berupa bilangan bulat.")
        if self.width < 1 or self.height < 1:
            raise BatikAssetError("Ukuran asset harus positif.")
        if not isinstance(self.metadata, dict):
            raise BatikAssetError("Metadata asset harus berupa object JSON.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


def load_batik_asset(
    content: bytes | bytearray | memoryview,
    *,
    filename: str = "asset.png",
    default_category: str = "ornamen",
) -> EditableBatikAsset:
    """Load a `.batikasset` JSON package or wrap ordinary PNG/JPEG bytes."""

    raw = bytes(content)
    if not raw:
        raise BatikAssetError("File asset kosong.")
    stripped = raw.lstrip()
    if stripped.startswith(b"{"):
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BatikAssetError("File .batikasset bukan JSON yang valid.") from exc
        return _asset_from_data(data)

    try:
        raster = normalize_raster_image(raw)
    except ValueError as exc:
        raise BatikAssetError(str(exc)) from exc
    stem = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    return EditableBatikAsset(
        name=stem.strip() or "Asset Batik",
        category=default_category,
        content=raster.content,
        width=raster.width,
        height=raster.height,
        metadata={"original_name": filename, "source_format": raster.source_format},
    )


def encode_batik_asset(asset: EditableBatikAsset) -> bytes:
    """Serialize a reusable asset as UTF-8 JSON with embedded canonical PNG."""

    if not isinstance(asset, EditableBatikAsset):
        raise BatikAssetError("asset harus berupa EditableBatikAsset.")
    data = {
        "format": ASSET_FORMAT,
        "schema_version": ASSET_SCHEMA_VERSION,
        "name": asset.name,
        "category": asset.category,
        "width": asset.width,
        "height": asset.height,
        "metadata": dict(asset.metadata),
        "png_base64": base64.b64encode(asset.content).decode("ascii"),
    }
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def humanize_raster_asset(
    content: bytes,
    *,
    seed: int = 2026,
    edge_wobble: float = 0.18,
    ink_breaks: float = 0.08,
    opacity_variation: float = 0.12,
) -> bytes:
    """Add deterministic imperfections resembling hand-applied malam/ink.

    The operation preserves transparency and source dimensions. It intentionally avoids
    pure random pixel noise: low-frequency warping, uneven opacity, and sparse ink gaps
    produce a more controlled handmade appearance.
    """

    wobble = _unit(edge_wobble, "Ketidakteraturan tepi")
    breaks = _unit(ink_breaks, "Celah malam")
    variation = _unit(opacity_variation, "Variasi tekanan")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise BatikAssetError("Seed humanize harus berupa bilangan bulat.")
    image = _open_rgba(content)
    rng = random.Random(seed)

    if wobble > 0:
        image = _mesh_warp(image, rng, wobble)
    alpha = image.getchannel("A")
    if variation > 0:
        alpha = _vary_opacity(alpha, rng, variation)
    if breaks > 0:
        alpha = _add_ink_breaks(alpha, rng, breaks)
    image.putalpha(alpha)

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _asset_from_data(data: object) -> EditableBatikAsset:
    if not isinstance(data, dict):
        raise BatikAssetError("Isi .batikasset harus berupa object JSON.")
    required = {
        "format",
        "schema_version",
        "name",
        "category",
        "width",
        "height",
        "metadata",
        "png_base64",
    }
    if set(data) != required:
        raise BatikAssetError("Struktur .batikasset tidak lengkap atau memiliki field asing.")
    if data["format"] != ASSET_FORMAT or data["schema_version"] != ASSET_SCHEMA_VERSION:
        raise BatikAssetError("Format atau versi .batikasset tidak didukung.")
    try:
        png = base64.b64decode(data["png_base64"], validate=True)
    except (TypeError, ValueError) as exc:
        raise BatikAssetError("Data PNG Base64 pada asset rusak.") from exc
    image = _open_rgba(png)
    if image.size != (data["width"], data["height"]):
        raise BatikAssetError("Ukuran metadata asset tidak cocok dengan PNG sumber.")
    metadata = data["metadata"]
    if not isinstance(metadata, dict):
        raise BatikAssetError("Metadata asset harus berupa object JSON.")
    return EditableBatikAsset(
        name=data["name"],
        category=data["category"],
        content=png,
        width=data["width"],
        height=data["height"],
        metadata=metadata,
    )


def _mesh_warp(image: Image.Image, rng: random.Random, strength: float) -> Image.Image:
    width, height = image.size
    cells = max(3, min(8, round(min(width, height) / 96)))
    xs = [round(width * index / cells) for index in range(cells + 1)]
    ys = [round(height * index / cells) for index in range(cells + 1)]
    amplitude = max(0.25, min(width, height) * 0.018 * strength)
    displacement: dict[tuple[int, int], tuple[float, float]] = {}
    for row in range(cells + 1):
        for column in range(cells + 1):
            border = row in {0, cells} or column in {0, cells}
            factor = 0.35 if border else 1.0
            displacement[(column, row)] = (
                rng.uniform(-amplitude, amplitude) * factor,
                rng.uniform(-amplitude, amplitude) * factor,
            )

    mesh: list[tuple[tuple[int, int, int, int], tuple[float, ...]]] = []
    for row in range(cells):
        for column in range(cells):
            left, right = xs[column], xs[column + 1]
            top, bottom = ys[row], ys[row + 1]
            d00 = displacement[(column, row)]
            d10 = displacement[(column + 1, row)]
            d11 = displacement[(column + 1, row + 1)]
            d01 = displacement[(column, row + 1)]
            quad = (
                left + d00[0],
                top + d00[1],
                left + d01[0],
                bottom + d01[1],
                right + d11[0],
                bottom + d11[1],
                right + d10[0],
                top + d10[1],
            )
            mesh.append(((left, top, right, bottom), quad))
    return image.transform(
        image.size,
        Image.Transform.MESH,
        mesh,
        resample=Image.Resampling.BICUBIC,
    )


def _vary_opacity(alpha: Image.Image, rng: random.Random, strength: float) -> Image.Image:
    low_width = max(3, min(24, alpha.width // 24))
    low_height = max(3, min(24, alpha.height // 24))
    noise = Image.new("L", (low_width, low_height))
    minimum = round(255 * (1 - 0.55 * strength))
    noise.putdata([rng.randint(minimum, 255) for _ in range(low_width * low_height)])
    noise = noise.resize(alpha.size, Image.Resampling.BICUBIC)
    return ImageChops.multiply(alpha, noise)


def _add_ink_breaks(alpha: Image.Image, rng: random.Random, strength: float) -> Image.Image:
    mask = Image.new("L", alpha.size, 255)
    draw = ImageDraw.Draw(mask)
    area = alpha.width * alpha.height
    count = max(1, min(240, round(area / 18_000 * strength * 12)))
    short_side = min(alpha.size)
    for _ in range(count):
        x = rng.randrange(alpha.width)
        y = rng.randrange(alpha.height)
        radius_x = rng.uniform(0.003, 0.014) * short_side * (0.35 + strength)
        radius_y = rng.uniform(0.002, 0.009) * short_side * (0.35 + strength)
        draw.ellipse(
            (x - radius_x, y - radius_y, x + radius_x, y + radius_y),
            fill=rng.randint(0, 80),
        )
    softened = mask.filter(ImageEnhance.Sharpness(mask).enhance(0.7).filter if False else None)
    # Keep the implementation Pillow-version stable: a direct multiply already gives
    # sparse wax/ink gaps and avoids requiring optional image-processing libraries.
    del softened
    return ImageChops.multiply(alpha, mask)


def _open_rgba(content: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            return source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BatikAssetError("PNG sumber asset tidak dapat dibaca.") from exc


def _unit(value: float, label: str) -> float:
    if isinstance(value, bool):
        raise BatikAssetError(f"{label} harus berupa angka 0–1.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BatikAssetError(f"{label} harus berupa angka 0–1.") from exc
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise BatikAssetError(f"{label} harus berada antara 0 dan 1.")
    return number


__all__ = [
    "ASSET_CATEGORIES",
    "ASSET_FORMAT",
    "ASSET_SCHEMA_VERSION",
    "BatikAssetError",
    "EditableBatikAsset",
    "encode_batik_asset",
    "humanize_raster_asset",
    "load_batik_asset",
]
