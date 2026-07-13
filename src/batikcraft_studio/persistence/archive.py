"""Safe, atomic save/open support for ``.batikcraft`` project archives."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from batikcraft_studio.domain import Project
from batikcraft_studio.persistence.errors import (
    ArchiveOpenError,
    ArchiveSaveError,
    ArchiveValidationError,
    AssetIntegrityError,
    CorruptArchiveError,
    DuplicateArchiveEntryError,
    MissingAssetError,
    MissingManifestError,
)
from batikcraft_studio.persistence.manifest import (
    AssetRecord,
    project_from_manifest,
    project_to_manifest,
)
from batikcraft_studio.persistence.paths import MANIFEST_PATH, normalize_archive_path

PROJECT_EXTENSION = ".batikcraft"
MAX_ARCHIVE_ENTRIES = 4096
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 128 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ProjectBundle:
    """A loaded project and its verified in-memory binary assets."""

    project: Project
    assets: Mapping[str, bytes]

    def __post_init__(self) -> None:
        if not isinstance(self.project, Project):
            raise ArchiveValidationError("project must be a Project aggregate.")
        normalized: dict[str, bytes] = {}
        seen: set[str] = set()
        for raw_path, content in self.assets.items():
            path = normalize_archive_path(raw_path)
            collision_key = path.casefold()
            if collision_key in seen:
                raise DuplicateArchiveEntryError(f"Duplicate asset path: {path!r}.")
            if not isinstance(content, bytes):
                raise ArchiveValidationError("Loaded asset values must be bytes.")
            seen.add(collision_key)
            normalized[path] = content
        object.__setattr__(self, "assets", MappingProxyType(normalized))

    def get_asset(self, path: str) -> bytes:
        """Return an asset by canonical archive path."""

        normalized = normalize_archive_path(path)
        try:
            return self.assets[normalized]
        except KeyError as exc:
            raise MissingAssetError(f"Asset {normalized!r} is not loaded.") from exc


class ProjectArchive:
    """Read and write versioned BatikCraft project containers."""

    @staticmethod
    def save(
        destination: str | os.PathLike[str],
        project: Project,
        assets: Mapping[str, bytes] | None = None,
    ) -> Path:
        """Atomically write a project and mark it saved only after replacement succeeds."""

        target = _project_path(destination)
        asset_bytes = _normalize_asset_mapping(assets or {})
        records = tuple(
            AssetRecord(path=path, size=len(content), sha256=hashlib.sha256(content).hexdigest())
            for path, content in asset_bytes.items()
        )
        manifest = project_to_manifest(project, records)
        manifest_bytes = json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        if len(manifest_bytes) > MAX_MANIFEST_BYTES:
            raise ArchiveValidationError("project.json exceeds the maximum supported size.")

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
                for path in sorted(asset_bytes):
                    archive.writestr(path, asset_bytes[path])

            with temporary_path.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary_path, target)
            project.mark_saved()
            return target
        except ArchiveValidationError:
            raise
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise ArchiveSaveError(f"Unable to save project archive {target}: {exc}") from exc
        finally:
            if temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    @staticmethod
    def load(source: str | os.PathLike[str]) -> ProjectBundle:
        """Load and verify an archive without extracting members to disk."""

        path = _project_path(source)
        if not path.exists():
            raise ArchiveOpenError(f"Project archive does not exist: {path}")
        if not path.is_file():
            raise ArchiveOpenError(f"Project archive is not a file: {path}")

        try:
            with zipfile.ZipFile(path, mode="r") as archive:
                infos = _validated_infos(archive)
                info_by_path = {info.filename: info for info in infos}
                manifest_info = info_by_path.get(MANIFEST_PATH)
                if manifest_info is None:
                    raise MissingManifestError("Archive does not contain project.json.")
                if manifest_info.file_size > MAX_MANIFEST_BYTES:
                    raise CorruptArchiveError("project.json exceeds the maximum supported size.")

                manifest_bytes = archive.read(manifest_info)
                try:
                    manifest_data = json.loads(manifest_bytes.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise CorruptArchiveError("project.json is not valid UTF-8 JSON.") from exc

                project, records = project_from_manifest(manifest_data)
                declared = {record.path: record for record in records}
                actual_assets = set(info_by_path) - {MANIFEST_PATH}
                declared_assets = set(declared)
                missing = declared_assets - actual_assets
                unexpected = actual_assets - declared_assets
                if missing:
                    raise MissingAssetError(
                        f"Archive is missing declared assets: {', '.join(sorted(missing))}."
                    )
                if unexpected:
                    raise CorruptArchiveError(
                        f"Archive contains undeclared files: {', '.join(sorted(unexpected))}."
                    )

                assets: dict[str, bytes] = {}
                for asset_path in sorted(declared):
                    record = declared[asset_path]
                    content = archive.read(info_by_path[asset_path])
                    if len(content) != record.size:
                        raise AssetIntegrityError(
                            f"Asset size mismatch for {asset_path!r}: "
                            f"expected {record.size}, got {len(content)}."
                        )
                    digest = hashlib.sha256(content).hexdigest()
                    if digest != record.sha256:
                        raise AssetIntegrityError(
                            f"Asset SHA-256 mismatch for {asset_path!r}."
                        )
                    assets[asset_path] = content
                return ProjectBundle(project=project, assets=assets)
        except (
            ArchiveValidationError,
            ArchiveOpenError,
            AssetIntegrityError,
            CorruptArchiveError,
            MissingAssetError,
            MissingManifestError,
        ):
            raise
        except (zipfile.BadZipFile, EOFError, OSError, RuntimeError) as exc:
            raise CorruptArchiveError(f"Unable to read project archive {path}: {exc}") from exc


def _project_path(value: str | os.PathLike[str]) -> Path:
    try:
        path = Path(value)
    except TypeError as exc:
        raise ArchiveValidationError("Project archive path must be path-like.") from exc
    if path.suffix.casefold() != PROJECT_EXTENSION:
        raise ArchiveValidationError(
            f"Project archive path must end with {PROJECT_EXTENSION}."
        )
    return path


def _normalize_asset_mapping(assets: Mapping[str, bytes]) -> dict[str, bytes]:
    if not isinstance(assets, Mapping):
        raise ArchiveValidationError("assets must be a mapping of archive paths to bytes.")
    normalized: dict[str, bytes] = {}
    seen: set[str] = set()
    total_size = 0
    for raw_path, raw_content in assets.items():
        path = normalize_archive_path(raw_path)
        collision_key = path.casefold()
        if collision_key in seen:
            raise DuplicateArchiveEntryError(f"Duplicate asset path: {path!r}.")
        if not isinstance(raw_content, bytes):
            raise ArchiveValidationError(f"Asset {path!r} must contain bytes.")
        if len(raw_content) > MAX_ASSET_BYTES:
            raise ArchiveValidationError(f"Asset {path!r} exceeds the maximum supported size.")
        total_size += len(raw_content)
        if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise ArchiveValidationError("Project assets exceed the maximum total size.")
        seen.add(collision_key)
        normalized[path] = raw_content
    return normalized


def _validated_infos(archive: zipfile.ZipFile) -> tuple[zipfile.ZipInfo, ...]:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise CorruptArchiveError("Archive contains too many entries.")

    validated: list[zipfile.ZipInfo] = []
    seen: set[str] = set()
    total_uncompressed = 0
    for info in infos:
        if info.is_dir():
            raise CorruptArchiveError("Directory entries are not permitted in project archives.")
        path = normalize_archive_path(info.filename, allow_manifest=True)
        if path != info.filename:
            raise CorruptArchiveError(f"Archive member path is not canonical: {info.filename!r}.")
        collision_key = path.casefold()
        if collision_key in seen:
            raise DuplicateArchiveEntryError(f"Duplicate archive entry: {path!r}.")
        if info.flag_bits & 0x1:
            raise CorruptArchiveError(f"Encrypted archive entry is not supported: {path!r}.")
        if path == MANIFEST_PATH:
            if info.file_size > MAX_MANIFEST_BYTES:
                raise CorruptArchiveError("project.json exceeds the maximum supported size.")
        elif info.file_size > MAX_ASSET_BYTES:
            raise CorruptArchiveError(f"Archive asset {path!r} exceeds the maximum size.")
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES + MAX_MANIFEST_BYTES:
            raise CorruptArchiveError("Archive exceeds the maximum total uncompressed size.")
        seen.add(collision_key)
        validated.append(info)
    return tuple(validated)
