"""Install, index, search, and remove large offline Batik asset packs."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from batikcraft_studio.imaging.batik_asset import ASSET_CATEGORIES, load_batik_asset

ASSET_PACK_FORMAT = "batikcraft-asset-pack"
ASSET_PACK_SCHEMA_VERSION = "1.0"
ASSET_PACK_EXTENSION = ".batikpack"
_MANIFEST_NAME = "manifest.json"
_MAX_PACK_FILES = 100_000
_MAX_MANIFEST_BYTES = 32 * 1024 * 1024
_MAX_SINGLE_ASSET_BYTES = 64 * 1024 * 1024


class AssetLibraryError(RuntimeError):
    """Raised when an installed pack or pack archive is invalid."""


@dataclass(frozen=True, slots=True)
class AssetRecord:
    """One searchable asset entry inside an installed pack."""

    pack_id: str
    asset_id: str
    name: str
    category: str
    relative_path: str
    tags: tuple[str, ...] = ()
    width: int | None = None
    height: int | None = None
    thumbnail_path: str | None = None
    metadata: Mapping[str, Any] | None = None

    @property
    def key(self) -> str:
        return f"{self.pack_id}:{self.asset_id}"


@dataclass(frozen=True, slots=True)
class AssetPack:
    """Installed pack metadata and its indexed assets."""

    pack_id: str
    name: str
    version: str
    author: str
    description: str
    root: Path
    assets: tuple[AssetRecord, ...]


class AssetLibrary:
    """Persistent, filesystem-backed library optimized for many offline assets."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_asset_library_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self._packs: dict[str, AssetPack] = {}
        self.refresh()

    @property
    def packs(self) -> tuple[AssetPack, ...]:
        return tuple(sorted(self._packs.values(), key=lambda item: item.name.casefold()))

    @property
    def asset_count(self) -> int:
        return sum(len(pack.assets) for pack in self._packs.values())

    def refresh(self) -> tuple[AssetPack, ...]:
        """Rescan installed packs; invalid directories are skipped safely."""

        packs: dict[str, AssetPack] = {}
        for child in sorted(self.root.iterdir(), key=lambda item: item.name.casefold()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            manifest_path = child / _MANIFEST_NAME
            if not manifest_path.is_file():
                continue
            try:
                pack = _pack_from_manifest_path(manifest_path)
            except (AssetLibraryError, OSError, json.JSONDecodeError):
                continue
            packs[pack.pack_id] = pack
        self._packs = packs
        return self.packs

    def get_pack(self, pack_id: str) -> AssetPack:
        try:
            return self._packs[pack_id]
        except KeyError as exc:
            raise AssetLibraryError(f"Asset pack {pack_id!r} tidak terpasang.") from exc

    def get_asset(self, key: str) -> AssetRecord:
        if ":" not in key:
            raise AssetLibraryError("Kunci asset harus berbentuk pack_id:asset_id.")
        pack_id, asset_id = key.split(":", 1)
        pack = self.get_pack(pack_id)
        for item in pack.assets:
            if item.asset_id == asset_id:
                return item
        raise AssetLibraryError(f"Asset {key!r} tidak ditemukan.")

    def search(
        self,
        query: str = "",
        *,
        category: str | None = None,
        pack_id: str | None = None,
        limit: int | None = None,
    ) -> tuple[AssetRecord, ...]:
        """Search by name, ID, tags, category, and selected pack."""

        if category and category not in ASSET_CATEGORIES:
            raise AssetLibraryError(f"Kategori asset tidak didukung: {category!r}.")
        if limit is not None and (isinstance(limit, bool) or limit < 1):
            raise AssetLibraryError("Batas hasil pencarian harus positif.")
        needle = query.strip().casefold()
        source_packs = (
            (self.get_pack(pack_id),) if pack_id else tuple(self._packs.values())
        )
        matches: list[AssetRecord] = []
        for pack in source_packs:
            for item in pack.assets:
                if category and item.category != category:
                    continue
                haystack = " ".join(
                    (item.name, item.asset_id, item.category, *item.tags)
                ).casefold()
                if needle and needle not in haystack:
                    continue
                matches.append(item)
        matches.sort(key=lambda item: (item.category, item.name.casefold(), item.key))
        if limit is not None:
            matches = matches[:limit]
        return tuple(matches)

    def read_asset(self, item: AssetRecord | str) -> bytes:
        record = self.get_asset(item) if isinstance(item, str) else item
        pack = self.get_pack(record.pack_id)
        path = _safe_join(pack.root, record.relative_path)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise AssetLibraryError(f"Asset {record.name!r} tidak dapat dibaca.") from exc
        if not content:
            raise AssetLibraryError(f"Asset {record.name!r} kosong.")
        if len(content) > _MAX_SINGLE_ASSET_BYTES:
            raise AssetLibraryError(f"Asset {record.name!r} terlalu besar.")
        return content

    def read_thumbnail(self, item: AssetRecord | str) -> bytes | None:
        record = self.get_asset(item) if isinstance(item, str) else item
        if record.thumbnail_path is None:
            return None
        pack = self.get_pack(record.pack_id)
        path = _safe_join(pack.root, record.thumbnail_path)
        try:
            content = path.read_bytes()
        except OSError:
            return None
        return content or None

    def install_pack(self, archive_path: Path | str, *, replace: bool = False) -> AssetPack:
        """Validate and atomically install one `.batikpack` ZIP archive."""

        archive_path = Path(archive_path)
        if archive_path.suffix.casefold() != ASSET_PACK_EXTENSION:
            raise AssetLibraryError(
                f"Asset pack harus memakai ekstensi {ASSET_PACK_EXTENSION}."
            )
        if not archive_path.is_file():
            raise AssetLibraryError(f"File asset pack tidak ditemukan: {archive_path}")

        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                members = archive.infolist()
                if len(members) > _MAX_PACK_FILES:
                    raise AssetLibraryError("Asset pack memiliki terlalu banyak file.")
                manifest_member = _find_manifest_member(members)
                if manifest_member.file_size > _MAX_MANIFEST_BYTES:
                    raise AssetLibraryError("Manifest asset pack terlalu besar.")
                manifest = json.loads(archive.read(manifest_member).decode("utf-8"))
                pack_id = _validate_manifest(manifest)["pack"]["id"]
                destination = self.root / pack_id
                if destination.exists() and not replace:
                    raise AssetLibraryError(
                        f"Asset pack {pack_id!r} sudah terpasang. Gunakan replace untuk mengganti."
                    )
                with tempfile.TemporaryDirectory(
                    prefix=f".{pack_id}-",
                    dir=self.root,
                ) as temporary_dir:
                    staging = Path(temporary_dir) / "pack"
                    staging.mkdir()
                    _extract_validated_archive(archive, members, staging)
                    parsed = _pack_from_manifest_path(staging / _MANIFEST_NAME)
                    _validate_pack_files(parsed)
                    backup = self.root / f".{pack_id}.backup"
                    if backup.exists():
                        shutil.rmtree(backup)
                    if destination.exists():
                        destination.replace(backup)
                    try:
                        staging.replace(destination)
                    except Exception:
                        if backup.exists() and not destination.exists():
                            backup.replace(destination)
                        raise
                    finally:
                        if backup.exists():
                            shutil.rmtree(backup)
        except AssetLibraryError:
            raise
        except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AssetLibraryError("Asset pack rusak atau tidak valid.") from exc

        self.refresh()
        return self.get_pack(pack_id)

    def uninstall_pack(self, pack_id: str) -> None:
        """Remove an installed pack directory and refresh the index."""

        pack = self.get_pack(pack_id)
        try:
            shutil.rmtree(pack.root)
        except OSError as exc:
            raise AssetLibraryError(f"Asset pack {pack.name!r} gagal dihapus.") from exc
        self.refresh()


def default_asset_library_root() -> Path:
    """Return a per-user writable library path without third-party dependencies."""

    override = os.environ.get("BATIKCRAFT_ASSET_LIBRARY")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "BatikCraftStudio" / "asset-library"


def _find_manifest_member(members: Sequence[zipfile.ZipInfo]) -> zipfile.ZipInfo:
    candidates = [item for item in members if item.filename == _MANIFEST_NAME]
    if len(candidates) != 1:
        raise AssetLibraryError("Asset pack harus memiliki tepat satu manifest.json di root.")
    return candidates[0]


def _extract_validated_archive(
    archive: zipfile.ZipFile,
    members: Sequence[zipfile.ZipInfo],
    destination: Path,
) -> None:
    seen: set[str] = set()
    for member in members:
        normalized = _normalize_relative_path(member.filename, allow_directory=True)
        collision_key = normalized.casefold()
        if collision_key in seen:
            raise AssetLibraryError(f"Path ganda dalam asset pack: {normalized!r}.")
        seen.add(collision_key)
        if member.is_dir():
            (destination / normalized).mkdir(parents=True, exist_ok=True)
            continue
        if member.file_size > _MAX_SINGLE_ASSET_BYTES and normalized != _MANIFEST_NAME:
            raise AssetLibraryError(f"File asset terlalu besar: {normalized!r}.")
        output = _safe_join(destination, normalized)
        output.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member, "r") as source, output.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)


def _pack_from_manifest_path(manifest_path: Path) -> AssetPack:
    raw = manifest_path.read_bytes()
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise AssetLibraryError("Manifest asset pack terlalu besar.")
    manifest = json.loads(raw.decode("utf-8"))
    validated = _validate_manifest(manifest)
    pack_data = validated["pack"]
    assets = tuple(
        AssetRecord(
            pack_id=pack_data["id"],
            asset_id=item["id"],
            name=item["name"],
            category=item["category"],
            relative_path=item["file"],
            tags=tuple(item.get("tags", ())),
            width=item.get("width"),
            height=item.get("height"),
            thumbnail_path=item.get("thumbnail"),
            metadata=item.get("metadata", {}),
        )
        for item in validated["assets"]
    )
    return AssetPack(
        pack_id=pack_data["id"],
        name=pack_data["name"],
        version=pack_data["version"],
        author=pack_data.get("author", ""),
        description=pack_data.get("description", ""),
        root=manifest_path.parent,
        assets=assets,
    )


def _validate_manifest(data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AssetLibraryError("Manifest asset pack harus berupa JSON object.")
    required_root = {"format", "schema_version", "pack", "assets"}
    if set(data) != required_root:
        raise AssetLibraryError("Field root manifest asset pack tidak valid.")
    if data["format"] != ASSET_PACK_FORMAT:
        raise AssetLibraryError("Format asset pack tidak didukung.")
    if data["schema_version"] != ASSET_PACK_SCHEMA_VERSION:
        raise AssetLibraryError("Versi schema asset pack tidak didukung.")
    pack = data["pack"]
    if not isinstance(pack, dict):
        raise AssetLibraryError("Field pack harus berupa object.")
    required_pack = {"id", "name", "version"}
    allowed_pack = required_pack | {"author", "description"}
    if not required_pack.issubset(pack) or set(pack) - allowed_pack:
        raise AssetLibraryError("Metadata pack tidak lengkap atau memiliki field asing.")
    pack_id = _identifier(pack["id"], "pack id")
    pack_name = _text(pack["name"], "pack name", 160)
    version = _text(pack["version"], "pack version", 40)
    author = _text(pack.get("author", ""), "pack author", 160, allow_blank=True)
    description = _text(
        pack.get("description", ""),
        "pack description",
        2000,
        allow_blank=True,
    )

    assets = data["assets"]
    if not isinstance(assets, list):
        raise AssetLibraryError("Field assets harus berupa array.")
    normalized_assets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    for index, item in enumerate(assets):
        if not isinstance(item, dict):
            raise AssetLibraryError(f"assets[{index}] harus berupa object.")
        required_asset = {"id", "name", "category", "file"}
        allowed_asset = required_asset | {
            "tags",
            "width",
            "height",
            "thumbnail",
            "metadata",
        }
        if not required_asset.issubset(item) or set(item) - allowed_asset:
            raise AssetLibraryError(f"Field assets[{index}] tidak valid.")
        asset_id = _identifier(item["id"], f"assets[{index}].id")
        if asset_id in seen_ids:
            raise AssetLibraryError(f"ID asset ganda: {asset_id!r}.")
        seen_ids.add(asset_id)
        name = _text(item["name"], f"assets[{index}].name", 160)
        category = item["category"]
        if category not in ASSET_CATEGORIES:
            raise AssetLibraryError(f"Kategori asset tidak didukung: {category!r}.")
        relative_file = _normalize_relative_path(item["file"])
        if relative_file.casefold() in seen_files:
            raise AssetLibraryError(f"File asset ganda: {relative_file!r}.")
        seen_files.add(relative_file.casefold())
        tags_raw = item.get("tags", [])
        if not isinstance(tags_raw, list):
            raise AssetLibraryError(f"assets[{index}].tags harus berupa array.")
        tags = tuple(_text(tag, "tag", 60) for tag in tags_raw)
        width = _optional_positive_int(item.get("width"), "width")
        height = _optional_positive_int(item.get("height"), "height")
        thumbnail = item.get("thumbnail")
        if thumbnail is not None:
            thumbnail = _normalize_relative_path(thumbnail)
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            raise AssetLibraryError(f"assets[{index}].metadata harus berupa object.")
        normalized_assets.append(
            {
                "id": asset_id,
                "name": name,
                "category": category,
                "file": relative_file,
                "tags": tags,
                "width": width,
                "height": height,
                "thumbnail": thumbnail,
                "metadata": metadata,
            }
        )
    return {
        "format": ASSET_PACK_FORMAT,
        "schema_version": ASSET_PACK_SCHEMA_VERSION,
        "pack": {
            "id": pack_id,
            "name": pack_name,
            "version": version,
            "author": author,
            "description": description,
        },
        "assets": normalized_assets,
    }


def _validate_pack_files(pack: AssetPack) -> None:
    for item in pack.assets:
        asset_path = _safe_join(pack.root, item.relative_path)
        if not asset_path.is_file():
            raise AssetLibraryError(f"File asset tidak ditemukan: {item.relative_path!r}.")
        try:
            load_batik_asset(asset_path.read_bytes(), filename=asset_path.name)
        except (OSError, ValueError) as exc:
            raise AssetLibraryError(f"Asset {item.name!r} tidak valid.") from exc
        if item.thumbnail_path is not None:
            thumbnail = _safe_join(pack.root, item.thumbnail_path)
            if not thumbnail.is_file():
                raise AssetLibraryError(
                    f"Thumbnail asset tidak ditemukan: {item.thumbnail_path!r}."
                )


def _normalize_relative_path(value: object, *, allow_directory: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssetLibraryError("Path asset harus berupa string non-kosong.")
    raw = value.replace("\\", "/")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AssetLibraryError(f"Path asset tidak aman: {value!r}.")
    if ":" in path.parts[0]:
        raise AssetLibraryError(f"Path asset tidak aman: {value!r}.")
    normalized = path.as_posix().rstrip("/") if allow_directory else path.as_posix()
    if not normalized:
        raise AssetLibraryError("Path asset kosong.")
    return normalized


def _safe_join(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise AssetLibraryError(f"Path keluar dari root asset library: {relative_path!r}.") from exc
    return candidate


def _identifier(value: object, label: str) -> str:
    text = _text(value, label, 120)
    if not all(character.isalnum() or character in "-_." for character in text):
        raise AssetLibraryError(
            f"{label} hanya boleh berisi huruf, angka, titik, garis bawah, dan dash."
        )
    return text


def _text(value: object, label: str, maximum: int, *, allow_blank: bool = False) -> str:
    if not isinstance(value, str):
        raise AssetLibraryError(f"{label} harus berupa string.")
    text = value.strip()
    if not text and not allow_blank:
        raise AssetLibraryError(f"{label} tidak boleh kosong.")
    if len(text) > maximum:
        raise AssetLibraryError(f"{label} terlalu panjang.")
    return text


def _optional_positive_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AssetLibraryError(f"{label} harus berupa bilangan bulat positif.")
    return value


__all__ = [
    "ASSET_PACK_EXTENSION",
    "ASSET_PACK_FORMAT",
    "ASSET_PACK_SCHEMA_VERSION",
    "AssetLibrary",
    "AssetLibraryError",
    "AssetPack",
    "AssetRecord",
    "default_asset_library_root",
]
