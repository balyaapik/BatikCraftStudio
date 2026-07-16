"""Portable, checksummed artwork packages for the BatikCraft marketplace."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from PIL import Image, UnidentifiedImageError

from batikcraft_studio.domain import Project
from batikcraft_studio.persistence.errors import ArchiveValidationError
from batikcraft_studio.persistence.manifest import (
    AssetRecord,
    project_from_manifest,
    project_to_manifest,
)

BATIKCRAFT_NFT_EXTENSION = ".batikcraftnft"
BATIKCRAFT_NFT_FORMAT = "batikcraft-nft"
BATIKCRAFT_NFT_SCHEMA_VERSION = "1.0"
MANIFEST_PATH = "manifest.json"
SEAL_PATH = "seal.json"
PROJECT_MANIFEST_PATH = "project/project.json"
PREVIEW_PATH = "preview.jpg"
MAX_NFT_ENTRIES = 4096
MAX_NFT_FILE_BYTES = 128 * 1024 * 1024
MAX_NFT_TOTAL_BYTES = 768 * 1024 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class BatikNFTError(RuntimeError):
    """Base error for `.batikcraftnft` export and verification."""


class BatikNFTIntegrityError(BatikNFTError):
    """Raised when a package checksum or locked identity no longer matches."""


@dataclass(frozen=True, slots=True)
class NFTExportMetadata:
    """Marketplace metadata collected before exporting an artwork."""

    creator_user_id: str
    philosophy: str
    motifs: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    license_name: str = "All rights reserved"

    def __post_init__(self) -> None:
        creator_id = _non_blank(self.creator_user_id, "creator_user_id", 120)
        philosophy = _non_blank(self.philosophy, "philosophy", 5_000)
        motifs = _normalized_text_list(self.motifs, "motif", 80, 50)
        colors = _normalized_colors(self.colors)
        license_name = _non_blank(self.license_name, "license_name", 200)
        object.__setattr__(self, "creator_user_id", creator_id)
        object.__setattr__(self, "philosophy", philosophy)
        object.__setattr__(self, "motifs", motifs)
        object.__setattr__(self, "colors", colors)
        object.__setattr__(self, "license_name", license_name)


@dataclass(frozen=True, slots=True)
class NFTFileRecord:
    """Integrity record for one immutable package payload."""

    path: str
    role: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        path = _normalize_member_path(self.path)
        role = _non_blank(self.role, "role", 80)
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise BatikNFTError("Ukuran file NFT harus berupa bilangan bulat non-negatif.")
        if not isinstance(self.sha256, str) or not _SHA256_PATTERN.fullmatch(self.sha256):
            raise BatikNFTError("Checksum file NFT harus berupa SHA-256 lowercase.")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "role", role)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "role": self.role,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class BatikNFTBundle:
    """Verified package data suitable for a future marketplace uploader."""

    package_id: str
    manifest: Mapping[str, Any]
    project: Project
    project_assets: Mapping[str, bytes]
    preview_jpeg: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest", MappingProxyType(dict(self.manifest)))
        object.__setattr__(
            self,
            "project_assets",
            MappingProxyType(dict(self.project_assets)),
        )


def export_batikcraft_nft(
    destination: str | os.PathLike[str],
    project: Project,
    assets: Mapping[str, bytes],
    preview_jpeg: bytes,
    metadata: NFTExportMetadata,
) -> Path:
    """Write one deterministic, atomically replaced `.batikcraftnft` package."""

    if not isinstance(project, Project):
        raise BatikNFTError("project harus berupa Project BatikCraft.")
    if not isinstance(metadata, NFTExportMetadata):
        raise BatikNFTError("metadata NFT tidak valid.")
    _validate_jpeg(preview_jpeg)
    target = _nft_path(destination)
    normalized_assets = _normalize_assets(assets)
    asset_records = tuple(
        AssetRecord(path=path, size=len(content), sha256=_sha256(content))
        for path, content in sorted(normalized_assets.items())
    )
    try:
        project_manifest = project_to_manifest(project, asset_records)
    except ArchiveValidationError as exc:
        raise BatikNFTError(f"Project tidak dapat dikemas: {exc}") from exc
    project_manifest_bytes = _json_bytes(project_manifest, pretty=True)

    payload: dict[str, bytes] = {
        PREVIEW_PATH: bytes(preview_jpeg),
        PROJECT_MANIFEST_PATH: project_manifest_bytes,
    }
    for asset_path, content in normalized_assets.items():
        payload[f"project/{asset_path}"] = content

    records = tuple(
        NFTFileRecord(
            path=path,
            role=_role_for_path(path),
            size=len(content),
            sha256=_sha256(content),
        )
        for path, content in sorted(payload.items())
    )
    payload_root = _payload_root(records)
    identity = {
        "project_id": project.project_id,
        "title": project.metadata.title,
        "creator": {
            "user_id": metadata.creator_user_id,
            "display_name": project.metadata.creator,
        },
        "project_created_at": project.created_at.isoformat(),
    }
    package_id = _sha256(_canonical_json_bytes({"identity": identity, "payload_root": payload_root}))
    manifest = {
        "format": BATIKCRAFT_NFT_FORMAT,
        "schema_version": BATIKCRAFT_NFT_SCHEMA_VERSION,
        "package_id": package_id,
        "exported_at": datetime.now(UTC).isoformat(),
        "identity": identity,
        "artwork": {
            "description": project.metadata.description,
            "philosophy": metadata.philosophy,
            "motifs": list(metadata.motifs),
            "colors": list(metadata.colors),
            "tags": list(project.metadata.tags),
            "license": metadata.license_name,
            "canvas": {
                "width": project.canvas.width,
                "height": project.canvas.height,
                "background_color": project.canvas.background_color,
            },
        },
        "files": [record.to_dict() for record in records],
        "integrity": {
            "algorithm": "SHA-256",
            "payload_root_sha256": payload_root,
            "identity_locked": True,
            "digital_signature": False,
            "note": (
                "Perubahan identitas atau payload membatalkan checksum. "
                "Paket ini belum menggunakan tanda tangan kunci publik."
            ),
        },
    }
    manifest_bytes = _json_bytes(manifest, pretty=True)
    seal = {
        "format": "batikcraft-nft-seal",
        "schema_version": BATIKCRAFT_NFT_SCHEMA_VERSION,
        "package_id": package_id,
        "manifest_sha256": _sha256(manifest_bytes),
        "payload_root_sha256": payload_root,
    }
    seal_bytes = _json_bytes(seal, pretty=True)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            archive.writestr(MANIFEST_PATH, manifest_bytes)
            archive.writestr(SEAL_PATH, seal_bytes)
            for path in sorted(payload):
                archive.writestr(path, payload[path])
        with temporary_path.open("r+b") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
        return target
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise BatikNFTError(f"Gagal menulis paket NFT {target}: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_batikcraft_nft(source: str | os.PathLike[str]) -> BatikNFTBundle:
    """Load and fully verify a `.batikcraftnft` package without extracting it."""

    path = _nft_path(source)
    if not path.is_file():
        raise BatikNFTError(f"Paket NFT tidak ditemukan: {path}")
    try:
        with zipfile.ZipFile(path, mode="r") as archive:
            infos = _validated_infos(archive)
            info_by_path = {info.filename: info for info in infos}
            if MANIFEST_PATH not in info_by_path or SEAL_PATH not in info_by_path:
                raise BatikNFTIntegrityError("Paket NFT tidak memiliki manifest atau seal.")
            manifest_bytes = archive.read(info_by_path[MANIFEST_PATH])
            seal_bytes = archive.read(info_by_path[SEAL_PATH])
            manifest = _decode_json(manifest_bytes, "manifest.json")
            seal = _decode_json(seal_bytes, "seal.json")
            _validate_manifest_header(manifest)
            _validate_seal(seal, manifest_bytes, manifest)
            records = _records_from_manifest(manifest)
            declared = {record.path: record for record in records}
            actual = set(info_by_path) - {MANIFEST_PATH, SEAL_PATH}
            if actual != set(declared):
                missing = sorted(set(declared) - actual)
                unexpected = sorted(actual - set(declared))
                detail = []
                if missing:
                    detail.append(f"hilang: {', '.join(missing)}")
                if unexpected:
                    detail.append(f"tidak dideklarasikan: {', '.join(unexpected)}")
                raise BatikNFTIntegrityError("Isi paket tidak cocok dengan manifest (" + "; ".join(detail) + ").")

            payload: dict[str, bytes] = {}
            for record in records:
                content = archive.read(info_by_path[record.path])
                if len(content) != record.size or _sha256(content) != record.sha256:
                    raise BatikNFTIntegrityError(
                        f"Checksum atau ukuran file berubah: {record.path}"
                    )
                payload[record.path] = content
            payload_root = _payload_root(records)
            integrity = _mapping(manifest.get("integrity"), "integrity")
            if integrity.get("payload_root_sha256") != payload_root:
                raise BatikNFTIntegrityError("Payload root SHA-256 tidak cocok.")
            identity = _mapping(manifest.get("identity"), "identity")
            expected_package_id = _sha256(
                _canonical_json_bytes({"identity": identity, "payload_root": payload_root})
            )
            package_id = manifest.get("package_id")
            if package_id != expected_package_id:
                raise BatikNFTIntegrityError("Package ID tidak cocok dengan identitas terkunci.")

            project_manifest_bytes = payload.get(PROJECT_MANIFEST_PATH)
            preview = payload.get(PREVIEW_PATH)
            if project_manifest_bytes is None or preview is None:
                raise BatikNFTIntegrityError("Project atau preview wajib tidak ditemukan.")
            project_manifest = _decode_json(project_manifest_bytes, PROJECT_MANIFEST_PATH)
            try:
                project, project_records = project_from_manifest(project_manifest)
            except ArchiveValidationError as exc:
                raise BatikNFTIntegrityError(f"Manifest project tidak valid: {exc}") from exc
            project_assets: dict[str, bytes] = {}
            for project_record in project_records:
                package_asset_path = f"project/{project_record.path}"
                content = payload.get(package_asset_path)
                if content is None:
                    raise BatikNFTIntegrityError(
                        f"Asset project tidak ditemukan: {project_record.path}"
                    )
                if len(content) != project_record.size or _sha256(content) != project_record.sha256:
                    raise BatikNFTIntegrityError(
                        f"Integritas asset project gagal: {project_record.path}"
                    )
                project_assets[project_record.path] = content
            _validate_locked_identity(identity, project)
            _validate_jpeg(preview)
            return BatikNFTBundle(
                package_id=str(package_id),
                manifest=manifest,
                project=project,
                project_assets=project_assets,
                preview_jpeg=preview,
            )
    except BatikNFTError:
        raise
    except (OSError, EOFError, RuntimeError, zipfile.BadZipFile) as exc:
        raise BatikNFTError(f"Paket NFT tidak dapat dibaca: {exc}") from exc


def _validate_locked_identity(identity: Mapping[str, Any], project: Project) -> None:
    creator = _mapping(identity.get("creator"), "identity.creator")
    checks = {
        "project_id": project.project_id,
        "title": project.metadata.title,
        "project_created_at": project.created_at.isoformat(),
    }
    for key, expected in checks.items():
        if identity.get(key) != expected:
            raise BatikNFTIntegrityError(f"Identitas terkunci berubah pada field {key}.")
    if creator.get("display_name") != project.metadata.creator:
        raise BatikNFTIntegrityError("Nama kreator tidak cocok dengan project tersemat.")
    _non_blank(str(creator.get("user_id", "")), "identity.creator.user_id", 120)


def _validate_manifest_header(manifest: Mapping[str, Any]) -> None:
    if manifest.get("format") != BATIKCRAFT_NFT_FORMAT:
        raise BatikNFTIntegrityError("Format paket NFT tidak didukung.")
    if manifest.get("schema_version") != BATIKCRAFT_NFT_SCHEMA_VERSION:
        raise BatikNFTIntegrityError("Versi schema paket NFT tidak didukung.")
    package_id = manifest.get("package_id")
    if not isinstance(package_id, str) or not _SHA256_PATTERN.fullmatch(package_id):
        raise BatikNFTIntegrityError("Package ID harus berupa SHA-256.")


def _validate_seal(
    seal: Mapping[str, Any],
    manifest_bytes: bytes,
    manifest: Mapping[str, Any],
) -> None:
    expected = {
        "format": "batikcraft-nft-seal",
        "schema_version": BATIKCRAFT_NFT_SCHEMA_VERSION,
        "package_id": manifest.get("package_id"),
        "manifest_sha256": _sha256(manifest_bytes),
        "payload_root_sha256": _mapping(manifest.get("integrity"), "integrity").get(
            "payload_root_sha256"
        ),
    }
    if dict(seal) != expected:
        raise BatikNFTIntegrityError("Seal paket NFT tidak cocok dengan manifest.")


def _records_from_manifest(manifest: Mapping[str, Any]) -> tuple[NFTFileRecord, ...]:
    raw_records = manifest.get("files")
    if not isinstance(raw_records, list):
        raise BatikNFTIntegrityError("files pada manifest harus berupa list.")
    records: list[NFTFileRecord] = []
    seen: set[str] = set()
    for raw in raw_records:
        if not isinstance(raw, dict) or set(raw) != {"path", "role", "size", "sha256"}:
            raise BatikNFTIntegrityError("Struktur record file NFT tidak valid.")
        try:
            record = NFTFileRecord(
                path=raw["path"],
                role=raw["role"],
                size=raw["size"],
                sha256=raw["sha256"],
            )
        except (BatikNFTError, TypeError, ValueError) as exc:
            raise BatikNFTIntegrityError(str(exc)) from exc
        key = record.path.casefold()
        if key in seen:
            raise BatikNFTIntegrityError(f"Record file NFT duplikat: {record.path}")
        seen.add(key)
        records.append(record)
    return tuple(sorted(records, key=lambda item: item.path))


def _validated_infos(archive: zipfile.ZipFile) -> tuple[zipfile.ZipInfo, ...]:
    infos = archive.infolist()
    if len(infos) > MAX_NFT_ENTRIES:
        raise BatikNFTIntegrityError("Paket NFT memiliki terlalu banyak file.")
    total = 0
    seen: set[str] = set()
    for info in infos:
        if info.is_dir():
            raise BatikNFTIntegrityError("Folder entry tidak diizinkan dalam paket NFT.")
        path = _normalize_member_path(info.filename)
        if path != info.filename:
            raise BatikNFTIntegrityError(f"Path file NFT tidak kanonik: {info.filename}")
        key = path.casefold()
        if key in seen:
            raise BatikNFTIntegrityError(f"File NFT duplikat: {path}")
        if info.flag_bits & 0x1:
            raise BatikNFTIntegrityError(f"File NFT terenkripsi tidak didukung: {path}")
        if info.file_size > MAX_NFT_FILE_BYTES:
            raise BatikNFTIntegrityError(f"File NFT terlalu besar: {path}")
        total += info.file_size
        if total > MAX_NFT_TOTAL_BYTES:
            raise BatikNFTIntegrityError("Ukuran total paket NFT melebihi batas.")
        seen.add(key)
    return tuple(infos)


def _normalize_assets(assets: Mapping[str, bytes]) -> dict[str, bytes]:
    if not isinstance(assets, Mapping):
        raise BatikNFTError("assets harus berupa mapping.")
    normalized: dict[str, bytes] = {}
    for raw_path, raw_content in assets.items():
        path = str(raw_path)
        if path.startswith("/") or "\\" in path or ".." in PurePosixPath(path).parts:
            raise BatikNFTError(f"Path asset project tidak aman: {path}")
        if not isinstance(raw_content, bytes):
            raise BatikNFTError(f"Asset {path} harus berupa bytes.")
        normalized[path] = raw_content
    return normalized


def _validate_jpeg(content: bytes) -> None:
    if not isinstance(content, bytes) or not content:
        raise BatikNFTError("Preview JPEG tidak tersedia.")
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
            if image.format != "JPEG":
                raise BatikNFTError("Preview paket NFT harus berformat JPEG.")
    except BatikNFTError:
        raise
    except (OSError, UnidentifiedImageError) as exc:
        raise BatikNFTError("Preview JPEG tidak dapat dibaca.") from exc


def _payload_root(records: tuple[NFTFileRecord, ...]) -> str:
    data = [record.to_dict() for record in sorted(records, key=lambda item: item.path)]
    return _sha256(_canonical_json_bytes(data))


def _role_for_path(path: str) -> str:
    if path == PREVIEW_PATH:
        return "preview"
    if path == PROJECT_MANIFEST_PATH:
        return "project-manifest"
    return "project-asset"


def _nft_path(value: str | os.PathLike[str]) -> Path:
    path = Path(value)
    if path.suffix.casefold() != BATIKCRAFT_NFT_EXTENSION:
        raise BatikNFTError(
            f"Nama paket harus berakhiran {BATIKCRAFT_NFT_EXTENSION}."
        )
    return path


def _normalize_member_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        raise BatikNFTError("Path file NFT tidak aman.")
    parts = PurePosixPath(value).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise BatikNFTError("Path file NFT tidak aman.")
    normalized = PurePosixPath(*parts).as_posix()
    if normalized != value:
        raise BatikNFTError("Path file NFT harus kanonik.")
    return normalized


def _decode_json(content: bytes, owner: str) -> dict[str, Any]:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BatikNFTIntegrityError(f"{owner} bukan JSON UTF-8 valid.") from exc
    if not isinstance(value, dict):
        raise BatikNFTIntegrityError(f"{owner} harus berupa object JSON.")
    return value


def _mapping(value: object, owner: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BatikNFTIntegrityError(f"{owner} harus berupa object JSON.")
    return value


def _json_bytes(value: object, *, pretty: bool) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_json_bytes(value: object) -> bytes:
    return _json_bytes(value, pretty=False)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _non_blank(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise BatikNFTError(f"{field} harus berupa teks.")
    normalized = value.strip()
    if not normalized:
        raise BatikNFTError(f"{field} wajib diisi.")
    if len(normalized) > maximum:
        raise BatikNFTError(f"{field} maksimal {maximum} karakter.")
    return normalized


def _normalized_text_list(
    values: tuple[str, ...],
    field: str,
    item_maximum: int,
    count_maximum: int,
) -> tuple[str, ...]:
    if isinstance(values, str):
        raise BatikNFTError(f"{field} harus berupa kumpulan teks.")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _non_blank(raw, field, item_maximum)
        key = value.casefold()
        if key not in seen:
            normalized.append(value)
            seen.add(key)
    if len(normalized) > count_maximum:
        raise BatikNFTError(f"Terlalu banyak {field}; maksimal {count_maximum}.")
    return tuple(normalized)


def _normalized_colors(values: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(values, str):
        raise BatikNFTError("colors harus berupa kumpulan kode HEX.")
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str) or not _COLOR_PATTERN.fullmatch(raw.strip()):
            raise BatikNFTError(f"Warna NFT tidak valid: {raw!r}")
        color = raw.strip().upper()
        if color not in seen:
            result.append(color)
            seen.add(color)
    if len(result) > 64:
        raise BatikNFTError("Palet NFT maksimal memuat 64 warna.")
    return tuple(result)


__all__ = [
    "BATIKCRAFT_NFT_EXTENSION",
    "BATIKCRAFT_NFT_FORMAT",
    "BATIKCRAFT_NFT_SCHEMA_VERSION",
    "BatikNFTBundle",
    "BatikNFTError",
    "BatikNFTIntegrityError",
    "NFTExportMetadata",
    "export_batikcraft_nft",
    "load_batikcraft_nft",
]
