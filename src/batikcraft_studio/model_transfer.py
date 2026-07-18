"""Byte-accurate, resumable transfer helpers for local and marketplace LoRA packs."""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from batikcraft_studio.dependency_bootstrap import default_managed_dependency_root
from batikcraft_studio.web_bridge import BatikCraftWebClient, BatikCraftWebError

TransferProgress = Callable[[int, int, str], object]
_CHUNK_SIZE = 256 * 1024


class ModelTransferCancelled(RuntimeError):
    """Raised after the active file stream has stopped because the user cancelled."""


def default_model_download_cache() -> Path:
    """Return the resumable marketplace model download cache."""

    return default_managed_dependency_root() / "cache" / "model-downloads"


def copy_model_pack_with_progress(
    source: str | Path,
    destination: str | Path,
    *,
    progress: TransferProgress | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Copy one local model pack while reporting real bytes and honoring cancel."""

    source_path = Path(source).expanduser()
    if not source_path.is_file():
        raise OSError(f"File model tidak ditemukan: {source_path}")
    target = Path(destination).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.part")
    total = source_path.stat().st_size
    copied = 0
    _report(progress, copied, total, source_path.name)
    try:
        with source_path.open("rb") as src, temporary.open("wb") as dst:
            while True:
                _raise_if_cancelled(cancel_event)
                chunk = src.read(_CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
                copied += len(chunk)
                _report(progress, copied, total, source_path.name)
        _raise_if_cancelled(cancel_event)
        temporary.replace(target)
    except ModelTransferCancelled:
        temporary.unlink(missing_ok=True)
        raise
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def download_marketplace_model(
    client: BatikCraftWebClient,
    model_id: int,
    *,
    progress: TransferProgress | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Download one `.batikmodel` with Content-Length progress, resume, and cancel."""

    if not client.token:
        raise BatikCraftWebError("Login ke BatikCraftWeb terlebih dahulu.")
    cache = default_model_download_cache()
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"model-{int(model_id)}.batikmodel"
    partial = target.with_suffix(target.suffix + ".part")
    existing = partial.stat().st_size if partial.is_file() else 0
    headers = {
        "Accept": "application/octet-stream",
        "Authorization": f"Token {client.token}",
    }
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(
        client._api_url(f"models/{int(model_id)}/download/"),
        method="GET",
        headers=headers,
    )

    try:
        with urllib.request.urlopen(request, timeout=client.timeout) as response:
            status = int(getattr(response, "status", response.getcode()) or 200)
            content_length = _header_int(response.headers.get("Content-Length"))
            total = _content_range_total(response.headers.get("Content-Range"))
            if status == 206 and existing > 0:
                mode = "ab"
                downloaded = existing
                if total <= 0:
                    total = existing + content_length
            else:
                mode = "wb"
                downloaded = 0
                total = content_length
            _report(progress, downloaded, total, target.name)
            with partial.open(mode) as stream:
                while True:
                    _raise_if_cancelled(cancel_event)
                    chunk = response.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    stream.write(chunk)
                    downloaded += len(chunk)
                    _report(progress, downloaded, total, target.name)
            _raise_if_cancelled(cancel_event)
            partial.replace(target)
            _report(progress, downloaded, total or downloaded, target.name)
            return target
    except ModelTransferCancelled:
        # Keep the partial file so the next attempt can continue with an HTTP Range.
        raise
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and partial.is_file():
            partial.replace(target)
            return target
        if exc.code == 401:
            raise BatikCraftWebError("Login tidak valid atau sesi sudah berakhir.") from exc
        raise BatikCraftWebError(
            f"Website menolak unduhan model ({exc.code}): {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise BatikCraftWebError(
            f"Tidak dapat mengunduh model dari {client.base_url}: {exc.reason}"
        ) from exc


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise ModelTransferCancelled(
            "Unduhan model dibatalkan. File parsial disimpan agar dapat dilanjutkan."
        )


def _report(
    callback: TransferProgress | None,
    completed: int,
    total: int,
    filename: str,
) -> None:
    if callback is not None:
        callback(max(0, int(completed)), max(0, int(total)), filename)


def _header_int(value: object) -> int:
    try:
        return max(0, int(str(value or "0")))
    except (TypeError, ValueError):
        return 0


def _content_range_total(value: object) -> int:
    text = str(value or "")
    if "/" not in text:
        return 0
    return _header_int(text.rsplit("/", 1)[-1])


__all__ = [
    "ModelTransferCancelled",
    "copy_model_pack_with_progress",
    "default_model_download_cache",
    "download_marketplace_model",
]
