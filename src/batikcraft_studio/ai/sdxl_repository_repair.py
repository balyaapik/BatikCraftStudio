"""Make Online SDXL repair compare local files against repository byte metadata."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from batikcraft_studio.ai import runtime_model_installer
from batikcraft_studio.ai.model_connectivity import model_online

_INSTALLED = False


def install_sdxl_repository_repair() -> None:
    """Patch BatikBrew installation so Online repair never trusts names alone."""

    global _INSTALLED
    if _INSTALLED:
        return

    original = runtime_model_installer.install_batikbrew_runtime
    if getattr(original, "_batikcraft_repository_repair", False):
        _INSTALLED = True
        return

    def install_verified(
        root: str | Path | None = None,
        *,
        progress: Any = None,
        cancel_event: threading.Event | None = None,
        snapshot_download_func: Any = None,
    ) -> Any:
        if not model_online():
            return original(
                root,
                progress=progress,
                cancel_event=cancel_event,
                snapshot_download_func=snapshot_download_func,
            )

        # In Online mode every repair pass must ask the repository for its current file
        # metadata. The original downloader already compares each remote byte size with
        # the local file and skips only exact matches. Temporarily bypass its early
        # structure-only return so this reconciliation always runs.
        original_find = runtime_model_installer.find_installed_batikbrew_runtime
        original_complete = runtime_model_installer._sdxl_model_is_complete
        runtime_model_installer.find_installed_batikbrew_runtime = (  # type: ignore[assignment]
            lambda _root=None: None
        )
        runtime_model_installer._sdxl_model_is_complete = (  # type: ignore[attr-defined]
            lambda _path: False
        )
        try:
            return original(
                root,
                progress=progress,
                cancel_event=cancel_event,
                snapshot_download_func=snapshot_download_func,
            )
        finally:
            runtime_model_installer.find_installed_batikbrew_runtime = original_find
            runtime_model_installer._sdxl_model_is_complete = original_complete  # type: ignore[attr-defined]

    install_verified._batikcraft_repository_repair = True  # type: ignore[attr-defined]
    runtime_model_installer.install_batikbrew_runtime = install_verified  # type: ignore[assignment]
    _INSTALLED = True


__all__ = ["install_sdxl_repository_repair"]
