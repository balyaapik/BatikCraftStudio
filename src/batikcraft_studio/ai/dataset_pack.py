"""Portable offline training datasets for BatikCraft LoRA workflows."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

BATIK_DATASET_FORMAT = "batikcraft-training-dataset"
BATIK_DATASET_SCHEMA_VERSION = "1.0"
BATIK_DATASET_EXTENSION = ".batikdataset"
_DATASET_MANIFEST = "manifest.json"
_IMAGE_ROLES = ("source", "target", "conditioning", "mask")
_ID_PATTERN = re.compile(r"[^a-z0-9._-]+")


class BatikDatasetError(RuntimeError):
    """Raised when a training dataset is incomplete, unsafe, or malformed."""


@dataclass(frozen=True, slots=True)
class BatikDatasetMetadata:
    """Human-readable metadata embedded in one dataset archive."""

    dataset_id: str
    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    base_model_family: str = "sd15"
    trigger_word: str = "bcr_batik"

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", safe_identifier(self.dataset_id))
        object.__setattr__(self, "name", _text(self.name, "dataset name", 160))
        object.__setattr__(self, "version", _text(self.version, "dataset version", 40))
        object.__setattr__(self, "author", _optional_text(self.author, 160))
        object.__setattr__(self, "description", _optional_text(self.description, 2_000))
        object.__setattr__(
            self,
            "base_model_family",
            _text(self.base_model_family, "base model family", 80),
        )
        trigger = _text(self.trigger_word, "trigger word", 80)
        if any(character.isspace() for character in trigger):
            raise BatikDatasetError("trigger_word tidak boleh mengandung spasi.")
        object.__setattr__(self, "trigger_word", trigger)


@dataclass(frozen=True, slots=True)
class BatikTrainingSample:
    """One captioned source/target pair used for LoRA or paired training."""

    caption: str
    target_content: bytes
    source_content: bytes | None = None
    conditioning_content: bytes | None = None
    mask_content: bytes | None = None
    category: str = "lainnya"
    style: str = ""
    target_roles: tuple[str, ...] = ("main-render",)
    sample_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sample_id", safe_identifier(self.sample_id))
        caption = _text(self.caption, "caption", 1_000)
        object.__setattr__(self, "caption", caption)
        object.__setattr__(self, "category", _text(self.category, "category", 80))
        object.__setattr__(self, "style", _optional_text(self.style, 120))
        roles = tuple(dict.fromkeys(_text(role, "target role", 80) for role in self.target_roles))
        if not roles:
            raise BatikDatasetError("target_roles tidak boleh kosong.")
        object.__setattr__(self, "target_roles", roles)
        object.__setattr__(self, "target_content", _canonical_png(self.target_content, "target"))
        for field_name in ("source_content", "conditioning_content", "mask_content"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _canonical_png(value, field_name))
        if not isinstance(self.metadata, dict):
            raise BatikDatasetError("metadata sample harus berupa dictionary.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class BatikDatasetBundle:
    """Validated dataset metadata and immutable samples."""

    metadata: BatikDatasetMetadata
    samples: tuple[BatikTrainingSample, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, BatikDatasetMetadata):
            raise BatikDatasetError("metadata dataset tidak valid.")
        if not self.samples:
            raise BatikDatasetError("Dataset harus memiliki minimal satu sample.")
        ids = [sample.sample_id for sample in self.samples]
        if len(ids) != len(set(ids)):
            raise BatikDatasetError("sample_id harus unik.")


def build_batik_dataset(
    samples: tuple[BatikTrainingSample, ...] | list[BatikTrainingSample],
    metadata: BatikDatasetMetadata,
    destination: Path | str,
) -> Path:
    """Write a deterministic, checksum-protected `.batikdataset` archive."""

    bundle = BatikDatasetBundle(metadata=metadata, samples=tuple(samples))
    output = Path(destination)
    if output.suffix.casefold() != BATIK_DATASET_EXTENSION:
        output = output.with_suffix(BATIK_DATASET_EXTENSION)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    manifest_samples: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for sample in bundle.samples:
                files: dict[str, str] = {}
                checksums: dict[str, str] = {}
                contents = {
                    "target": sample.target_content,
                    "source": sample.source_content,
                    "conditioning": sample.conditioning_content,
                    "mask": sample.mask_content,
                }
                for role, content in contents.items():
                    if content is None:
                        continue
                    path = f"samples/{sample.sample_id}/{role}.png"
                    archive.writestr(path, content)
                    files[role] = path
                    checksums[role] = hashlib.sha256(content).hexdigest()
                manifest_samples.append(
                    {
                        "id": sample.sample_id,
                        "caption": sample.caption,
                        "category": sample.category,
                        "style": sample.style,
                        "target_roles": list(sample.target_roles),
                        "files": files,
                        "sha256": checksums,
                        "metadata": dict(sample.metadata),
                    }
                )
            manifest = {
                "format": BATIK_DATASET_FORMAT,
                "schema_version": BATIK_DATASET_SCHEMA_VERSION,
                "dataset": {
                    "id": metadata.dataset_id,
                    "name": metadata.name,
                    "version": metadata.version,
                    "author": metadata.author,
                    "description": metadata.description,
                    "base_model_family": metadata.base_model_family,
                    "trigger_word": metadata.trigger_word,
                },
                "samples": manifest_samples,
            }
            archive.writestr(
                _DATASET_MANIFEST,
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode(
                    "utf-8"
                ),
            )
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return output


def load_batik_dataset(path: Path | str) -> BatikDatasetBundle:
    """Load and fully validate a `.batikdataset` archive."""

    archive_path = Path(path)
    if archive_path.suffix.casefold() != BATIK_DATASET_EXTENSION:
        raise BatikDatasetError(f"Dataset harus memakai ekstensi {BATIK_DATASET_EXTENSION}.")
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            members = archive.infolist()
            names = [_safe_member_name(member.filename) for member in members]
            if len(names) != len(set(name.casefold() for name in names)):
                raise BatikDatasetError("Dataset memiliki path ganda.")
            if names.count(_DATASET_MANIFEST) != 1:
                raise BatikDatasetError("Dataset harus memiliki satu manifest.json.")
            manifest = json.loads(archive.read(_DATASET_MANIFEST).decode("utf-8"))
            metadata, rows = _validate_manifest(manifest)
            samples: list[BatikTrainingSample] = []
            available = set(names)
            for row in rows:
                files = row["files"]
                checksums = row["sha256"]
                contents: dict[str, bytes | None] = {role: None for role in _IMAGE_ROLES}
                for role, member_name in files.items():
                    normalized = _safe_member_name(member_name)
                    if normalized not in available:
                        raise BatikDatasetError(f"File sample tidak ditemukan: {normalized}")
                    content = archive.read(normalized)
                    expected = checksums.get(role)
                    if hashlib.sha256(content).hexdigest() != expected:
                        raise BatikDatasetError(
                            f"Checksum sample {row['id']} untuk {role} tidak cocok."
                        )
                    contents[role] = content
                samples.append(
                    BatikTrainingSample(
                        sample_id=row["id"],
                        caption=row["caption"],
                        category=row["category"],
                        style=row["style"],
                        target_roles=tuple(row["target_roles"]),
                        target_content=contents["target"] or b"",
                        source_content=contents["source"],
                        conditioning_content=contents["conditioning"],
                        mask_content=contents["mask"],
                        metadata=row["metadata"],
                    )
                )
    except BatikDatasetError:
        raise
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BatikDatasetError("File dataset rusak atau tidak dapat dibaca.") from exc
    return BatikDatasetBundle(metadata=metadata, samples=tuple(samples))


def safe_identifier(value: object) -> str:
    """Normalize user labels into archive-safe identifiers."""

    text = str(value).strip().casefold().replace(" ", "-")
    text = _ID_PATTERN.sub("-", text).strip("-.")
    if not text:
        raise BatikDatasetError("Identifier tidak boleh kosong.")
    return text[:120]


def _validate_manifest(data: object) -> tuple[BatikDatasetMetadata, list[dict[str, Any]]]:
    if not isinstance(data, dict):
        raise BatikDatasetError("Manifest dataset harus berupa object JSON.")
    if set(data) != {"format", "schema_version", "dataset", "samples"}:
        raise BatikDatasetError("Field root manifest dataset tidak valid.")
    if data["format"] != BATIK_DATASET_FORMAT:
        raise BatikDatasetError("Format dataset tidak didukung.")
    if data["schema_version"] != BATIK_DATASET_SCHEMA_VERSION:
        raise BatikDatasetError("Versi schema dataset tidak didukung.")
    dataset = data["dataset"]
    if not isinstance(dataset, dict):
        raise BatikDatasetError("Metadata dataset tidak valid.")
    required_dataset = {
        "id",
        "name",
        "version",
        "author",
        "description",
        "base_model_family",
        "trigger_word",
    }
    if set(dataset) != required_dataset:
        raise BatikDatasetError("Field metadata dataset tidak lengkap.")
    metadata = BatikDatasetMetadata(
        dataset_id=dataset["id"],
        name=dataset["name"],
        version=dataset["version"],
        author=dataset["author"],
        description=dataset["description"],
        base_model_family=dataset["base_model_family"],
        trigger_word=dataset["trigger_word"],
    )
    rows = data["samples"]
    if not isinstance(rows, list) or not rows:
        raise BatikDatasetError("Manifest tidak memiliki sample.")
    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    required_row = {
        "id",
        "caption",
        "category",
        "style",
        "target_roles",
        "files",
        "sha256",
        "metadata",
    }
    for raw in rows:
        if not isinstance(raw, dict) or set(raw) != required_row:
            raise BatikDatasetError("Struktur sample pada manifest tidak valid.")
        sample_id = safe_identifier(raw["id"])
        if sample_id in seen_ids:
            raise BatikDatasetError("sample_id ganda pada manifest.")
        seen_ids.add(sample_id)
        files = raw["files"]
        checksums = raw["sha256"]
        if not isinstance(files, dict) or "target" not in files:
            raise BatikDatasetError("Setiap sample harus memiliki target.")
        if set(files) - set(_IMAGE_ROLES) or not isinstance(checksums, dict):
            raise BatikDatasetError("Role file sample tidak valid.")
        if set(files) != set(checksums):
            raise BatikDatasetError("Checksum file sample tidak lengkap.")
        for role, digest in checksums.items():
            if role not in _IMAGE_ROLES or not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
                raise BatikDatasetError("Checksum sample tidak valid.")
        target_roles = raw["target_roles"]
        if not isinstance(target_roles, list) or not target_roles:
            raise BatikDatasetError("target_roles sample tidak valid.")
        if not isinstance(raw["metadata"], dict):
            raise BatikDatasetError("metadata sample tidak valid.")
        validated.append(
            {
                "id": sample_id,
                "caption": _text(raw["caption"], "caption", 1_000),
                "category": _text(raw["category"], "category", 80),
                "style": _optional_text(raw["style"], 120),
                "target_roles": [_text(role, "target role", 80) for role in target_roles],
                "files": {str(role): str(name) for role, name in files.items()},
                "sha256": {str(role): str(digest) for role, digest in checksums.items()},
                "metadata": dict(raw["metadata"]),
            }
        )
    return metadata, validated


def _canonical_png(content: bytes, label: str) -> bytes:
    if not isinstance(content, bytes) or not content:
        raise BatikDatasetError(f"Image {label} kosong.")
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BatikDatasetError(f"Image {label} tidak dapat dibaca.") from exc
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _safe_member_name(value: object) -> str:
    text = str(value).replace("\\", "/")
    path = PurePosixPath(text)
    if (
        not text
        or path.is_absolute()
        or ".." in path.parts
        or any(part in {"", "."} for part in path.parts)
    ):
        raise BatikDatasetError(f"Path archive tidak aman: {text!r}.")
    return path.as_posix()


def _text(value: object, label: str, maximum: int) -> str:
    text = str(value).strip()
    if not text:
        raise BatikDatasetError(f"{label} tidak boleh kosong.")
    if len(text) > maximum:
        raise BatikDatasetError(f"{label} terlalu panjang.")
    return text


def _optional_text(value: object, maximum: int) -> str:
    text = str(value).strip()
    if len(text) > maximum:
        raise BatikDatasetError("Metadata text terlalu panjang.")
    return text


__all__ = [
    "BATIK_DATASET_EXTENSION",
    "BATIK_DATASET_FORMAT",
    "BATIK_DATASET_SCHEMA_VERSION",
    "BatikDatasetBundle",
    "BatikDatasetError",
    "BatikDatasetMetadata",
    "BatikTrainingSample",
    "build_batik_dataset",
    "load_batik_dataset",
    "safe_identifier",
]
