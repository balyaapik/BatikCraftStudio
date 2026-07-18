"""Compatibility fixes applied before the desktop application imports AI modules."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from batikcraft_studio.dependency_bootstrap import default_managed_huggingface_cache_dir


def install_runtime_compatibility() -> None:
    """Apply storage and downloader compatibility before AI dialogs are imported."""

    _patch_runtime_cache_function()
    _patch_legacy_hf_hub_download()


def _patch_runtime_cache_function() -> None:
    """Make every runtime settings consumer use dependencies/cache/huggingface."""

    from batikcraft_studio.ai import runtime_settings

    runtime_settings.default_ai_cache_dir = default_managed_huggingface_cache_dir


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
        if tqdm_class is None:
            return original(*args, **kwargs)

        previous_tqdm = getattr(file_download, "tqdm", None)

        class LegacyCompatibleTqdm(tqdm_class):  # type: ignore[misc, valid-type]
            def __init__(self, *bar_args: object, **bar_kwargs: object) -> None:
                # Hub 0.x passes an internal progress-group name that plain tqdm does
                # not accept. BatikCraft already knows the active repository file.
                bar_kwargs.pop("name", None)
                super().__init__(*bar_args, **bar_kwargs)

        try:
            if previous_tqdm is not None:
                file_download.tqdm = LegacyCompatibleTqdm
            return original(*args, **kwargs)
        finally:
            if previous_tqdm is not None:
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


__all__ = ["install_runtime_compatibility"]
