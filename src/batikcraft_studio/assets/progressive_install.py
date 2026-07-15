"""Cancellable, progress-reporting installation for large Batik asset packs."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from batikcraft_studio.imaging.batik_asset import load_batik_asset

from . import library as library_module

_COPY_CHUNK_SIZE = 1024 * 1024


class AssetInstallCancelled(library_module.AssetLibraryError):
    """Raised when the user cancels an install before the atomic commit stage."""


@dataclass(frozen=True, slots=True)
class AssetInstallProgress:
    """One immutable progress update emitted by a large pack installation."""

    stage: str
    fraction: float
    current: int
    total: int
    message: str
    cancellable: bool = True

    @property
    def percent(self) -> float:
        return min(100.0, max(0.0, self.fraction * 100.0))


ProgressCallback = Callable[[AssetInstallProgress], None]


def install_pack_with_progress(
    library: library_module.AssetLibrary,
    archive_path: Path | str,
    *,
    replace: bool = False,
    progress: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> library_module.AssetPack:
    """Validate and atomically install a pack while reporting real work progress.

    Extraction progress is based on uncompressed archive bytes. Validation progress
    is based on the number of declared assets. Cancellation is accepted only before
    the final filesystem swap, so an installed pack is never left half-replaced.
    """

    path = Path(archive_path)
    if path.suffix.casefold() != library_module.ASSET_PACK_EXTENSION:
        raise library_module.AssetLibraryError(
            f"Asset pack harus memakai ekstensi {library_module.ASSET_PACK_EXTENSION}."
        )
    if not path.is_file():
        raise library_module.AssetLibraryError(f"File asset pack tidak ditemukan: {path}")

    _emit(progress, "opening", 0.0, 0, 1, "Membuka paket asset…")
    _check_cancel(cancel_event)

    try:
        with zipfile.ZipFile(path, "r") as archive:
            members = archive.infolist()
            if len(members) > library_module._MAX_PACK_FILES:
                raise library_module.AssetLibraryError(
                    "Asset pack memiliki terlalu banyak file."
                )
            manifest_member = library_module._find_manifest_member(members)
            if manifest_member.file_size > library_module._MAX_MANIFEST_BYTES:
                raise library_module.AssetLibraryError(
                    "Manifest asset pack terlalu besar."
                )

            manifest = json.loads(archive.read(manifest_member).decode("utf-8"))
            validated = library_module._validate_manifest(manifest)
            pack_data = validated["pack"]
            pack_id = pack_data["id"]
            destination = library.root / pack_id
            if destination.exists() and not replace:
                raise library_module.AssetLibraryError(
                    f"Asset pack {pack_id!r} sudah terpasang. "
                    "Gunakan replace untuk mengganti."
                )

            asset_total = len(validated["assets"])
            _emit(
                progress,
                "manifest",
                0.05,
                asset_total,
                asset_total,
                f"Manifest valid: {asset_total} asset ditemukan.",
            )
            _check_cancel(cancel_event)

            with tempfile.TemporaryDirectory(
                prefix=f".{pack_id}-",
                dir=library.root,
            ) as temporary_dir:
                staging = Path(temporary_dir) / "pack"
                staging.mkdir()
                _extract_archive_with_progress(
                    archive,
                    members,
                    staging,
                    progress=progress,
                    cancel_event=cancel_event,
                )
                parsed = library_module._pack_from_manifest_path(
                    staging / "manifest.json"
                )
                _validate_pack_with_progress(
                    parsed,
                    progress=progress,
                    cancel_event=cancel_event,
                )
                _check_cancel(cancel_event)
                _emit(
                    progress,
                    "committing",
                    0.97,
                    1,
                    1,
                    "Menyelesaikan pemasangan secara atomik…",
                    cancellable=False,
                )
                _commit_staging(library.root, staging, destination, pack_id)
    except AssetInstallCancelled:
        raise
    except library_module.AssetLibraryError:
        raise
    except (
        OSError,
        zipfile.BadZipFile,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise library_module.AssetLibraryError(
            "Asset pack rusak atau tidak valid."
        ) from exc

    library.refresh()
    installed = library.get_pack(pack_id)
    _emit(
        progress,
        "complete",
        1.0,
        len(installed.assets),
        len(installed.assets),
        f"Paket {installed.name} selesai dipasang.",
        cancellable=False,
    )
    return installed


def _extract_archive_with_progress(
    archive: zipfile.ZipFile,
    members: Sequence[zipfile.ZipInfo],
    destination: Path,
    *,
    progress: ProgressCallback | None,
    cancel_event: Event | None,
) -> None:
    files = tuple(member for member in members if not member.is_dir())
    total_bytes = max(1, sum(max(0, member.file_size) for member in files))
    copied_bytes = 0
    seen: set[str] = set()

    for member in members:
        _check_cancel(cancel_event)
        normalized = library_module._normalize_relative_path(
            member.filename,
            allow_directory=True,
        )
        collision_key = normalized.casefold()
        if collision_key in seen:
            raise library_module.AssetLibraryError(
                f"Path ganda dalam asset pack: {normalized!r}."
            )
        seen.add(collision_key)
        if member.is_dir():
            (destination / normalized).mkdir(parents=True, exist_ok=True)
            continue
        if (
            member.file_size > library_module._MAX_SINGLE_ASSET_BYTES
            and normalized != "manifest.json"
        ):
            raise library_module.AssetLibraryError(
                f"File asset terlalu besar: {normalized!r}."
            )

        output = library_module._safe_join(destination, normalized)
        output.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member, "r") as source, output.open("wb") as target:
            while True:
                _check_cancel(cancel_event)
                chunk = source.read(_COPY_CHUNK_SIZE)
                if not chunk:
                    break
                target.write(chunk)
                copied_bytes += len(chunk)
                fraction = 0.05 + 0.55 * min(1.0, copied_bytes / total_bytes)
                _emit(
                    progress,
                    "extracting",
                    fraction,
                    copied_bytes,
                    total_bytes,
                    f"Mengekstrak {normalized}",
                )


def _validate_pack_with_progress(
    pack: library_module.AssetPack,
    *,
    progress: ProgressCallback | None,
    cancel_event: Event | None,
) -> None:
    total = max(1, len(pack.assets))
    for index, item in enumerate(pack.assets, start=1):
        _check_cancel(cancel_event)
        asset_path = library_module._safe_join(pack.root, item.relative_path)
        if not asset_path.is_file():
            raise library_module.AssetLibraryError(
                f"File asset tidak ditemukan: {item.relative_path!r}."
            )
        try:
            load_batik_asset(asset_path.read_bytes(), filename=asset_path.name)
        except (OSError, ValueError) as exc:
            raise library_module.AssetLibraryError(
                f"Asset {item.name!r} tidak valid."
            ) from exc
        if item.thumbnail_path is not None:
            thumbnail = library_module._safe_join(pack.root, item.thumbnail_path)
            if not thumbnail.is_file():
                raise library_module.AssetLibraryError(
                    f"Thumbnail asset tidak ditemukan: {item.thumbnail_path!r}."
                )
        fraction = 0.60 + 0.35 * index / total
        _emit(
            progress,
            "validating",
            fraction,
            index,
            len(pack.assets),
            f"Memvalidasi asset {index}/{len(pack.assets)}: {item.name}",
        )


def _commit_staging(
    library_root: Path,
    staging: Path,
    destination: Path,
    pack_id: str,
) -> None:
    backup = library_root / f".{pack_id}.backup"
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


def _check_cancel(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise AssetInstallCancelled("Pemasangan paket asset dibatalkan.")


def _emit(
    callback: ProgressCallback | None,
    stage: str,
    fraction: float,
    current: int,
    total: int,
    message: str,
    *,
    cancellable: bool = True,
) -> None:
    if callback is None:
        return
    callback(
        AssetInstallProgress(
            stage=stage,
            fraction=min(1.0, max(0.0, float(fraction))),
            current=max(0, int(current)),
            total=max(0, int(total)),
            message=message,
            cancellable=cancellable,
        )
    )


__all__ = [
    "AssetInstallCancelled",
    "AssetInstallProgress",
    "ProgressCallback",
    "install_pack_with_progress",
]
