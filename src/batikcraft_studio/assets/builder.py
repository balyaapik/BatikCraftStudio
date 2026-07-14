"""Build curated `.batikasset` files and installable `.batikpack` archives."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from batikcraft_studio.assets.library import (
    ASSET_PACK_EXTENSION,
    ASSET_PACK_FORMAT,
    ASSET_PACK_SCHEMA_VERSION,
)
from batikcraft_studio.imaging.batik_asset import (
    ASSET_CATEGORIES,
    EditableBatikAsset,
    encode_batik_asset,
)

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
_ID_PATTERN = re.compile(r"[^a-z0-9._-]+")


class AssetPackBuildError(RuntimeError):
    """Raised when candidate preparation or pack creation cannot continue safely."""


@dataclass(frozen=True, slots=True)
class AssetPackMetadata:
    """Human-readable metadata written into an asset-pack manifest."""

    pack_id: str
    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "pack_id", safe_identifier(self.pack_id))
        object.__setattr__(self, "name", _required_text(self.name, "pack name", 160))
        object.__setattr__(
            self,
            "version",
            _required_text(self.version, "pack version", 40),
        )
        object.__setattr__(self, "author", _optional_text(self.author, 160))
        object.__setattr__(
            self,
            "description",
            _optional_text(self.description, 2000),
        )


@dataclass(frozen=True, slots=True)
class AssetCandidate:
    """One curated image and its metadata before packaging."""

    asset_id: str
    name: str
    category: str
    content: bytes
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", safe_identifier(self.asset_id))
        object.__setattr__(self, "name", _required_text(self.name, "asset name", 160))
        if self.category not in ASSET_CATEGORIES:
            raise AssetPackBuildError(
                f"Kategori asset tidak didukung: {self.category!r}."
            )
        if not isinstance(self.content, bytes) or not self.content:
            raise AssetPackBuildError("Candidate asset harus memiliki image bytes.")
        normalized_tags = tuple(
            dict.fromkeys(_required_text(tag, "tag", 60) for tag in self.tags)
        )
        if not isinstance(self.metadata, dict):
            raise AssetPackBuildError("Metadata candidate harus berupa dictionary.")
        object.__setattr__(self, "tags", normalized_tags)
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class PreparedAsset:
    """Canonical PNG and dimensions produced from one candidate."""

    candidate: AssetCandidate
    png: bytes
    width: int
    height: int
    thumbnail: bytes
    source_sha256: str


def discover_images(root: Path | str) -> tuple[Path, ...]:
    """Return supported dataset images recursively in deterministic order."""

    directory = Path(root)
    if not directory.is_dir():
        raise AssetPackBuildError(f"Dataset directory tidak ditemukan: {directory}")
    return tuple(
        sorted(
            (
                path
                for path in directory.rglob("*")
                if path.is_file() and path.suffix.casefold() in _IMAGE_EXTENSIONS
            ),
            key=lambda path: path.as_posix().casefold(),
        )
    )


def canonicalize_candidate(
    candidate: AssetCandidate,
    *,
    master_size: int = 1024,
    padding_ratio: float = 0.06,
    thumbnail_size: int = 192,
) -> PreparedAsset:
    """Trim transparency, fit inside a square master, and create a thumbnail."""

    if not 64 <= master_size <= 4096:
        raise AssetPackBuildError("master_size harus berada antara 64 dan 4096.")
    if not 0 <= padding_ratio <= 0.4:
        raise AssetPackBuildError("padding_ratio harus berada antara 0 dan 0.4.")
    if not 32 <= thumbnail_size <= 1024:
        raise AssetPackBuildError("thumbnail_size harus berada antara 32 dan 1024.")
    image = _open_rgba(candidate.content)
    alpha_bounds = image.getchannel("A").getbbox()
    if alpha_bounds is None:
        raise AssetPackBuildError(f"Asset {candidate.name!r} sepenuhnya transparan.")
    image = image.crop(alpha_bounds)
    available = max(1, round(master_size * (1 - 2 * padding_ratio)))
    image.thumbnail((available, available), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (master_size, master_size), (0, 0, 0, 0))
    left = (master_size - image.width) // 2
    top = (master_size - image.height) // 2
    canvas.alpha_composite(image, dest=(left, top))

    png_output = BytesIO()
    canvas.save(png_output, format="PNG", optimize=True)
    png = png_output.getvalue()

    thumbnail = ImageOps.contain(
        canvas,
        (thumbnail_size, thumbnail_size),
        method=Image.Resampling.LANCZOS,
    )
    thumb_canvas = Image.new(
        "RGBA",
        (thumbnail_size, thumbnail_size),
        (244, 233, 216, 255),
    )
    thumb_left = (thumbnail_size - thumbnail.width) // 2
    thumb_top = (thumbnail_size - thumbnail.height) // 2
    thumb_canvas.alpha_composite(thumbnail, dest=(thumb_left, thumb_top))
    thumb_output = BytesIO()
    thumb_canvas.convert("RGB").save(
        thumb_output,
        format="PNG",
        optimize=True,
    )
    return PreparedAsset(
        candidate=candidate,
        png=png,
        width=master_size,
        height=master_size,
        thumbnail=thumb_output.getvalue(),
        source_sha256=hashlib.sha256(candidate.content).hexdigest(),
    )


def write_review_csv(
    candidates: tuple[AssetCandidate, ...] | list[AssetCandidate],
    destination: Path | str,
) -> Path:
    """Write a human-curation queue that can be edited in Kaggle or a spreadsheet."""

    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "keep",
                "asset_id",
                "name",
                "category",
                "tags",
                "source_path",
                "confidence",
                "notes",
            ),
        )
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    "keep": "1",
                    "asset_id": candidate.asset_id,
                    "name": candidate.name,
                    "category": candidate.category,
                    "tags": "|".join(candidate.tags),
                    "source_path": candidate.metadata.get("source_path", ""),
                    "confidence": candidate.metadata.get("confidence", ""),
                    "notes": candidate.metadata.get("notes", ""),
                }
            )
    return output


def read_review_csv(
    review_csv: Path | str,
    candidate_files: Path | str,
) -> tuple[AssetCandidate, ...]:
    """Read approved rows and load their PNG files from a candidate directory."""

    review_path = Path(review_csv)
    candidate_root = Path(candidate_files)
    if not review_path.is_file():
        raise AssetPackBuildError(f"Review CSV tidak ditemukan: {review_path}")
    accepted: list[AssetCandidate] = []
    with review_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"keep", "asset_id", "name", "category", "tags"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise AssetPackBuildError("Kolom review CSV tidak lengkap.")
        for row_index, row in enumerate(reader, start=2):
            if str(row.get("keep", "")).strip().casefold() not in {
                "1",
                "true",
                "yes",
                "y",
                "keep",
            }:
                continue
            asset_id = safe_identifier(row.get("asset_id", ""))
            file_path = candidate_root / f"{asset_id}.png"
            if not file_path.is_file():
                raise AssetPackBuildError(
                    f"Candidate PNG pada baris {row_index} tidak ditemukan: {file_path}"
                )
            tags = tuple(
                tag.strip()
                for tag in str(row.get("tags", "")).split("|")
                if tag.strip()
            )
            accepted.append(
                AssetCandidate(
                    asset_id=asset_id,
                    name=str(row.get("name", "")),
                    category=str(row.get("category", "")),
                    content=file_path.read_bytes(),
                    tags=tags,
                    metadata={
                        "source_path": row.get("source_path", ""),
                        "confidence": row.get("confidence", ""),
                        "notes": row.get("notes", ""),
                    },
                )
            )
    return tuple(accepted)


def build_asset_pack(
    candidates: tuple[AssetCandidate, ...] | list[AssetCandidate],
    metadata: AssetPackMetadata,
    destination: Path | str,
    *,
    master_size: int = 1024,
    padding_ratio: float = 0.06,
    thumbnail_size: int = 192,
) -> Path:
    """Create an installable `.batikpack` archive from curated candidates."""

    output = Path(destination)
    if output.suffix.casefold() != ASSET_PACK_EXTENSION:
        output = output.with_suffix(ASSET_PACK_EXTENSION)
    output.parent.mkdir(parents=True, exist_ok=True)
    items = tuple(candidates)
    if not items:
        raise AssetPackBuildError("Tidak ada candidate asset yang akan dipaketkan.")
    ids = [item.asset_id for item in items]
    if len(ids) != len(set(ids)):
        raise AssetPackBuildError("Candidate asset_id harus unik.")
    prepared = tuple(
        canonicalize_candidate(
            item,
            master_size=master_size,
            padding_ratio=padding_ratio,
            thumbnail_size=thumbnail_size,
        )
        for item in items
    )

    manifest_assets: list[dict[str, Any]] = []
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for item in prepared:
                asset_id = item.candidate.asset_id
                asset_path = f"assets/{asset_id}.batikasset"
                thumbnail_path = f"thumbnails/{asset_id}.png"
                asset_metadata = {
                    **item.candidate.metadata,
                    "source_sha256": item.source_sha256,
                    "builder": "batikcraft-studio",
                    "builder_schema": "1.0",
                }
                asset = EditableBatikAsset(
                    name=item.candidate.name,
                    category=item.candidate.category,
                    content=item.png,
                    width=item.width,
                    height=item.height,
                    metadata=asset_metadata,
                )
                archive.writestr(asset_path, encode_batik_asset(asset))
                archive.writestr(thumbnail_path, item.thumbnail)
                manifest_assets.append(
                    {
                        "id": asset_id,
                        "name": item.candidate.name,
                        "category": item.candidate.category,
                        "file": asset_path,
                        "thumbnail": thumbnail_path,
                        "tags": list(item.candidate.tags),
                        "width": item.width,
                        "height": item.height,
                        "metadata": asset_metadata,
                    }
                )
            manifest = {
                "format": ASSET_PACK_FORMAT,
                "schema_version": ASSET_PACK_SCHEMA_VERSION,
                "pack": {
                    "id": metadata.pack_id,
                    "name": metadata.name,
                    "version": metadata.version,
                    "author": metadata.author,
                    "description": metadata.description,
                },
                "assets": manifest_assets,
            }
            archive.writestr(
                "manifest.json",
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ).encode("utf-8"),
            )
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return output


def safe_identifier(value: object) -> str:
    """Normalize arbitrary labels into stable manifest-safe identifiers."""

    text = str(value).strip().casefold().replace(" ", "-")
    text = _ID_PATTERN.sub("-", text).strip("-.")
    if not text:
        raise AssetPackBuildError("Identifier tidak boleh kosong.")
    return text[:120]


def _open_rgba(content: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            return ImageOps.exif_transpose(source).convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise AssetPackBuildError("Candidate image tidak dapat dibaca.") from exc


def _required_text(value: object, label: str, maximum: int) -> str:
    text = str(value).strip()
    if not text:
        raise AssetPackBuildError(f"{label} tidak boleh kosong.")
    if len(text) > maximum:
        raise AssetPackBuildError(f"{label} terlalu panjang.")
    return text


def _optional_text(value: object, maximum: int) -> str:
    text = str(value).strip()
    if len(text) > maximum:
        raise AssetPackBuildError("Metadata text terlalu panjang.")
    return text


__all__ = [
    "AssetCandidate",
    "AssetPackBuildError",
    "AssetPackMetadata",
    "PreparedAsset",
    "build_asset_pack",
    "canonicalize_candidate",
    "discover_images",
    "read_review_csv",
    "safe_identifier",
    "write_review_csv",
]
