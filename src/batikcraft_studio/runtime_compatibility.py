"""Compatibility fixes applied before the desktop application imports AI modules."""

from __future__ import annotations

import inspect
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from batikcraft_studio.dependency_bootstrap import (
    default_managed_huggingface_cache_dir,
    default_managed_model_library_dir,
    default_managed_runtime_model_dir,
)


class _NullTextStream:
    """Writable text stream used when PyInstaller windowed builds expose no console.

    PyInstaller sets ``sys.stdout`` and ``sys.stderr`` to ``None`` for Windows GUI
    executables. Some versions of tqdm and Hugging Face Hub still write to those
    streams even when a custom progress callback is supplied. This lightweight sink
    preserves their file-like contract without opening a terminal or retaining output
    in memory.
    """

    encoding = "utf-8"
    errors = "replace"
    newlines = None
    closed = False

    def write(self, value: object) -> int:
        text = value if isinstance(value, str) else str(value)
        return len(text)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def fileno(self) -> int:
        raise OSError("BatikCraft windowed output stream has no file descriptor")


_NULL_STDOUT = _NullTextStream()
_NULL_STDERR = _NullTextStream()


def ensure_windowed_text_streams() -> tuple[object, object]:
    """Guarantee writable stdout/stderr objects for console-less desktop builds."""

    if getattr(sys, "stdout", None) is None:
        sys.stdout = _NULL_STDOUT  # type: ignore[assignment]
    if getattr(sys, "stderr", None) is None:
        sys.stderr = _NULL_STDERR  # type: ignore[assignment]
    return sys.stdout, sys.stderr


def install_runtime_compatibility() -> None:
    """Apply downloader compatibility and repair paths before AI dialogs are imported."""

    ensure_windowed_text_streams()
    _patch_legacy_hf_hub_download()
    _patch_runtime_cache_function()
    _repair_stale_model_settings()


def _patch_runtime_cache_function() -> None:
    """Make every public cache helper resolve inside managed dependencies."""

    import batikcraft_studio.ai as ai_package
    from batikcraft_studio.ai import runtime_settings

    runtime_settings.default_ai_cache_dir = default_managed_huggingface_cache_dir
    ai_package.default_ai_cache_dir = default_managed_huggingface_cache_dir


def _legacy_relative_path(value: object, marker: str) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("\\", "/")
    lowered = normalized.casefold()
    marker_text = marker.casefold().strip("/")
    needle = f"/batikcraftstudio/{marker_text}"
    index = lowered.find(needle)
    if index < 0:
        return None
    suffix = normalized[index + len(needle) :].strip("/")
    return Path(*[part for part in suffix.split("/") if part])


def _managed_runtime_path(value: object) -> str:
    relative = _legacy_relative_path(value, "models/runtime")
    if relative is None:
        return str(value or "")
    return str(default_managed_runtime_model_dir() / relative)


def _managed_cache_path(value: object) -> str:
    relative = _legacy_relative_path(value, "models/huggingface")
    if relative is None:
        return str(default_managed_huggingface_cache_dir())
    return str(default_managed_huggingface_cache_dir() / relative)


def _managed_lora_path(value: object) -> str:
    text = str(value or "").strip()
    relative = _legacy_relative_path(text, "models")
    if relative is None or not relative.parts:
        return text
    if relative.parts[0].casefold() in {"runtime", "huggingface"}:
        return text
    return str(default_managed_model_library_dir() / relative)


def _repair_stale_model_settings() -> None:
    """Rewrite saved paths even when they came from another Windows user profile."""

    from batikcraft_studio.ai.batikbrew_model_settings import (
        get_batikbrew_model_settings_store,
    )
    from batikcraft_studio.ai.runtime_settings import get_ai_runtime_store

    runtime_store = get_ai_runtime_store()
    runtime = runtime_store.load()
    managed_cache = _managed_cache_path(runtime.cache_dir)
    managed_model = _managed_runtime_path(runtime.default_model)
    if managed_cache != runtime.cache_dir or managed_model != runtime.default_model:
        try:
            runtime_store.save(
                replace(
                    runtime,
                    cache_dir=managed_cache,
                    default_model=managed_model,
                )
            )
        except OSError:
            pass

    batikbrew_store = get_batikbrew_model_settings_store()
    batikbrew = batikbrew_store.load()
    managed_base = _managed_runtime_path(batikbrew.base_model_path)
    managed_lora = _managed_lora_path(batikbrew.lora_path)
    if managed_base != batikbrew.base_model_path or managed_lora != batikbrew.lora_path:
        try:
            batikbrew_store.save(
                replace(
                    batikbrew,
                    base_model_path=managed_base,
                    lora_path=managed_lora,
                )
            )
        except OSError:
            pass


def _patch_legacy_hf_hub_download() -> bool:
    """Backport ``tqdm_class`` support to Hugging Face Hub 0.x.

    BatikCraft's optional Diffusers/Transformers stack may install a Hugging Face Hub
    0.x release that shadows the newer copy bundled in the executable. Releases such
    as 0.35 support a custom progress class on ``snapshot_download`` but not on
    ``hf_hub_download``. The model installer intentionally downloads one file at a
    time so it can aggregate real bytes and cancel inside the active transfer.

    Older Hub releases call the module-level ``file_download.tqdm`` object for every
    chunk. This adapter temporarily replaces that object with BatikCraft's tracker,
    then restores it immediately after the file finishes or fails.
    """

    ensure_windowed_text_streams()
    try:
        import huggingface_hub
        from huggingface_hub import file_download
    except ImportError:
        return False

    current = getattr(huggingface_hub, "hf_hub_download", None)
    if current is None or getattr(current, "__batikcraft_tqdm_compat__", False):
        return False
    try:
        parameters = inspect.signature(current).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "tqdm_class" in parameters:
        return False

    original: Callable[..., Any] = current

    def compatible_hf_hub_download(
        *args: object,
        tqdm_class: type | None = None,
        **kwargs: object,
    ) -> Any:
        ensure_windowed_text_streams()
        if tqdm_class is None:
            return original(*args, **kwargs)

        previous_tqdm = getattr(file_download, "tqdm", None)

        class LegacyCompatibleTqdm(tqdm_class):  # type: ignore[misc, valid-type]
            def __init__(self, *bar_args: object, **bar_kwargs: object) -> None:
                # Hub 0.x passes an internal progress-group name that plain tqdm does
                # not accept. BatikCraft already knows the active repository file.
                bar_kwargs.pop("name", None)
                if bar_kwargs.get("file") is None:
                    bar_kwargs["file"] = sys.stderr or _NULL_STDERR
                super().__init__(*bar_args, **bar_kwargs)

        try:
            file_download.tqdm = LegacyCompatibleTqdm
            return original(*args, **kwargs)
        finally:
            file_download.tqdm = previous_tqdm

    compatible_hf_hub_download.__name__ = getattr(
        original,
        "__name__",
        "hf_hub_download",
    )
    compatible_hf_hub_download.__doc__ = getattr(original, "__doc__", None)
    compatible_hf_hub_download.__batikcraft_tqdm_compat__ = True  # type: ignore[attr-defined]
    huggingface_hub.hf_hub_download = compatible_hf_hub_download
    return True


__all__ = ["ensure_windowed_text_streams", "install_runtime_compatibility"]
