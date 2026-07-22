"""Simpan/muat dokumen raster ke berkas ``.batikpaint``.

Format: satu ZIP berisi ``document.json`` (metadata + urutan layer) dan satu
PNG per layer di ``layers/<layer_id>.png``. Sederhana, tahan banting, dan bisa
dibuka pihak lain karena isinya cuma PNG biasa.

Penyimpanan bersifat atomik: tulis ke berkas sementara lalu ganti nama, supaya
berkas lama tidak rusak kalau proses gagal di tengah jalan.
"""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path

from batikcraft_studio.imaging.raster_document import RasterDocument
from batikcraft_studio.imaging.raster_layer import RasterLayer, RasterLayerError

PAINT_EXTENSION = ".batikpaint"
_SCHEMA_VERSION = 1
_MANIFEST_NAME = "document.json"
_MAX_LAYERS = 512
_MAX_LAYER_BYTES = 256 * 1024 * 1024


class RasterArchiveError(RuntimeError):
    """Kesalahan simpan/muat dokumen raster."""


def _layer_path(layer_id: str) -> str:
    # layer_id adalah UUID; tetap disanitasi agar tidak ada path traversal.
    safe = "".join(ch for ch in layer_id if ch.isalnum() or ch in "-_")
    if not safe:
        raise RasterArchiveError("layer_id tidak sah.")
    return f"layers/{safe}.png"


def save_raster_document(path: str | Path, document: RasterDocument) -> Path:
    destination = Path(path)
    if destination.suffix.casefold() != PAINT_EXTENSION:
        destination = destination.with_suffix(PAINT_EXTENSION)

    manifest = {
        "schema_version": _SCHEMA_VERSION,
        "width": document.width,
        "height": document.height,
        "background_color": document.background_color,
        "active_index": document.active_index,
        "layers": [
            {
                "layer_id": layer.layer_id,
                "name": layer.name,
                "visible": layer.visible,
                "opacity": layer.opacity,
                "file": _layer_path(layer.layer_id),
            }
            for layer in document.layers
        ],
    }

    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(
        suffix=PAINT_EXTENSION, dir=str(destination.parent)
    )
    os.close(handle)
    tmp_path = Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                _MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2)
            )
            for layer in document.layers:
                archive.writestr(_layer_path(layer.layer_id), layer.to_png_bytes())
        os.replace(tmp_path, destination)
    except Exception as exc:  # noqa: BLE001
        tmp_path.unlink(missing_ok=True)
        raise RasterArchiveError(f"Gagal menyimpan dokumen: {exc}") from exc
    return destination


def load_raster_document(path: str | Path) -> RasterDocument:
    source = Path(path)
    if not source.is_file():
        raise RasterArchiveError(f"Berkas tidak ditemukan: {source}")
    try:
        with zipfile.ZipFile(source, "r") as archive:
            names = set(archive.namelist())
            if _MANIFEST_NAME not in names:
                raise RasterArchiveError("Manifest dokumen tidak ada.")
            manifest = json.loads(archive.read(_MANIFEST_NAME).decode("utf-8"))
            _validate_manifest(manifest)
            layers: list[RasterLayer] = []
            for entry in manifest["layers"]:
                file_name = str(entry["file"])
                if file_name not in names:
                    raise RasterArchiveError(f"Berkas layer hilang: {file_name}")
                info = archive.getinfo(file_name)
                if info.file_size > _MAX_LAYER_BYTES:
                    raise RasterArchiveError("Berkas layer terlalu besar.")
                content = archive.read(file_name)
                layers.append(
                    RasterLayer.from_png_bytes(
                        content,
                        name=str(entry.get("name", "Layer")),
                        layer_id=str(entry["layer_id"]),
                        visible=bool(entry.get("visible", True)),
                        opacity=float(entry.get("opacity", 1.0)),
                    )
                )
    except (zipfile.BadZipFile, KeyError, ValueError, RasterLayerError) as exc:
        raise RasterArchiveError(f"Dokumen rusak atau tidak sah: {exc}") from exc

    return RasterDocument(
        width=int(manifest["width"]),
        height=int(manifest["height"]),
        background_color=str(manifest.get("background_color", "#FFFFFF")),
        layers=layers,
        active_index=int(manifest.get("active_index", 0)),
    )


def _validate_manifest(manifest: object) -> None:
    if not isinstance(manifest, dict):
        raise RasterArchiveError("Manifest tidak sah.")
    if manifest.get("schema_version") != _SCHEMA_VERSION:
        raise RasterArchiveError("Versi dokumen tidak didukung.")
    layers = manifest.get("layers")
    if not isinstance(layers, list) or not layers:
        raise RasterArchiveError("Dokumen harus punya minimal satu layer.")
    if len(layers) > _MAX_LAYERS:
        raise RasterArchiveError("Jumlah layer melebihi batas.")
    for entry in layers:
        if not isinstance(entry, dict) or "layer_id" not in entry or "file" not in entry:
            raise RasterArchiveError("Entri layer tidak lengkap.")


__all__ = [
    "PAINT_EXTENSION",
    "RasterArchiveError",
    "load_raster_document",
    "save_raster_document",
]
