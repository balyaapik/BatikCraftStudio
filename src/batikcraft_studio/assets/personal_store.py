"""Persistent personal asset pack for images imported by the desktop user."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image

from batikcraft_studio.imaging.batik_asset import ASSET_CATEGORIES
from batikcraft_studio.imaging.raster import RasterImageError, normalize_raster_image

from .library import (
    ASSET_PACK_FORMAT,
    ASSET_PACK_SCHEMA_VERSION,
    AssetLibrary,
    AssetLibraryError,
    AssetRecord,
)

PERSONAL_PACK_ID = "user-imports"
PERSONAL_PACK_NAME = "Gambar Impor Saya"
SUPPORTED_IMAGE_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".jfif",
    ".tif",
    ".tiff",
    ".webp",
    ".bmp",
    ".gif",
    ".ico",
)

_WRITE_LOCK = threading.RLock()


class PersonalAssetStore:
    """Write normalized imported images into one searchable per-user asset pack."""

    def __init__(self, library: AssetLibrary) -> None:
        self.library = library

    def import_image(
        self,
        filename: str,
        content: bytes | bytearray | memoryview,
        *,
        category: str = "ornamen",
    ) -> AssetRecord:
        """Normalize, de-duplicate, thumbnail, and persist one external image."""

        if category not in ASSET_CATEGORIES:
            raise AssetLibraryError(f"Kategori asset tidak didukung: {category!r}.")
        try:
            raster = normalize_raster_image(content)
        except RasterImageError as exc:
            raise AssetLibraryError(str(exc)) from exc

        digest = hashlib.sha256(raster.content).hexdigest()
        asset_id = f"image-{digest[:24]}"
        pack_root = self.library.root / PERSONAL_PACK_ID
        manifest_path = pack_root / "manifest.json"
        asset_relative = f"assets/{asset_id}.png"
        thumbnail_relative = f"thumbnails/{asset_id}.png"
        original_name = Path(filename).name or f"{asset_id}.png"
        display_name = Path(original_name).stem.strip() or "Gambar Impor"

        with _WRITE_LOCK:
            manifest = self._read_or_create_manifest(manifest_path)
            existing = next(
                (
                    item
                    for item in manifest["assets"]
                    if item.get("metadata", {}).get("sha256") == digest
                ),
                None,
            )
            if existing is None:
                pack_root.mkdir(parents=True, exist_ok=True)
                asset_path = pack_root / asset_relative
                thumbnail_path = pack_root / thumbnail_relative
                asset_path.parent.mkdir(parents=True, exist_ok=True)
                thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
                self._atomic_write_bytes(asset_path, raster.content)
                self._atomic_write_bytes(thumbnail_path, _thumbnail_png(raster.content))
                manifest["assets"].append(
                    {
                        "id": asset_id,
                        "name": display_name[:160],
                        "category": category,
                        "file": asset_relative,
                        "tags": ["impor", "gambar-eksternal", raster.source_format.casefold()],
                        "width": raster.width,
                        "height": raster.height,
                        "thumbnail": thumbnail_relative,
                        "metadata": {
                            "sha256": digest,
                            "original_name": original_name,
                            "source_format": raster.source_format,
                            "imported_at": datetime.now(timezone.utc).isoformat(),
                            "personal_library": True,
                        },
                    }
                )
                manifest["assets"].sort(
                    key=lambda item: (str(item["name"]).casefold(), str(item["id"]))
                )
                self._atomic_write_json(manifest_path, manifest)

        self.library.refresh()
        return self.library.get_asset(f"{PERSONAL_PACK_ID}:{asset_id}")

    @staticmethod
    def _read_or_create_manifest(path: Path) -> dict[str, object]:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AssetLibraryError("Manifest pustaka gambar pribadi rusak.") from exc
            if not isinstance(data, dict) or not isinstance(data.get("assets"), list):
                raise AssetLibraryError("Manifest pustaka gambar pribadi tidak valid.")
            return data
        return {
            "format": ASSET_PACK_FORMAT,
            "schema_version": ASSET_PACK_SCHEMA_VERSION,
            "pack": {
                "id": PERSONAL_PACK_ID,
                "name": PERSONAL_PACK_NAME,
                "version": "1.0",
                "author": "Local User",
                "description": (
                    "Gambar yang dimasukkan melalui menu Insert, drag-and-drop, "
                    "atau clipboard sistem."
                ),
            },
            "assets": [],
        }

    @staticmethod
    def _atomic_write_bytes(path: Path, content: bytes) -> None:
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise AssetLibraryError(f"Gagal menyimpan asset pribadi: {path.name}") from exc

    @staticmethod
    def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
        encoded = json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        PersonalAssetStore._atomic_write_bytes(path, encoded)


def _thumbnail_png(content: bytes) -> bytes:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            thumbnail = source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise AssetLibraryError("Thumbnail gambar impor tidak dapat dibuat.") from exc
    thumbnail.thumbnail((256, 256), Image.Resampling.LANCZOS)
    output = BytesIO()
    thumbnail.save(output, format="PNG", optimize=True)
    return output.getvalue()


__all__ = [
    "PERSONAL_PACK_ID",
    "PERSONAL_PACK_NAME",
    "SUPPORTED_IMAGE_EXTENSIONS",
    "PersonalAssetStore",
]
