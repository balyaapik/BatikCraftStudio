"""Prevent the runtime installer dialog from displaying false success.

The actual download runs in a child process. The GUI creates every managed storage
folder before launch, requires a real worker event, and validates the exact SDXL
folder before turning the progress bar into 100%.
"""

from __future__ import annotations

import json
from typing import Any

from batikcraft_studio.ai.runtime_model_installer import batikbrew_runtime_model_paths
from batikcraft_studio.ai.sdxl_runtime_integrity import inspect_batikbrew_runtime
from batikcraft_studio.managed_storage import ensure_managed_storage
from batikcraft_studio.ui.ai_runtime_model_install_dialog import RuntimeModelInstallDialog

_INSTALLED = False
_EVENT_KINDS = {"progress", "complete", "cancelled", "error"}


def install_runtime_installer_completion_guard() -> None:
    """Validate storage, worker events, and the exact folder before success."""

    global _INSTALLED
    if _INSTALLED:
        return

    dialog_class = RuntimeModelInstallDialog
    if getattr(dialog_class, "_batikcraft_completion_guard", False):
        _INSTALLED = True
        return

    original_start_install = dialog_class._start_install
    original_enqueue_event_line = dialog_class._enqueue_event_line
    original_handle_event = dialog_class._handle_event

    def start_install(dialog: Any) -> None:
        dialog._batikcraft_worker_event_seen = False
        try:
            ensure_managed_storage()
            dialog.install_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            dialog.result = None
            dialog._finish(
                "Instalasi tidak dapat dimulai karena folder penyimpanan tidak tersedia.",
                success=False,
            )
            dialog.detail.configure(text=str(exc))
            return
        original_start_install(dialog)

    def enqueue_event_line(dialog: Any, line: str) -> bool:
        try:
            payload = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and str(payload.get("kind", "")) in _EVENT_KINDS:
            dialog._batikcraft_worker_event_seen = True
        return original_enqueue_event_line(dialog, line)

    def handle_event(dialog: Any, event: object) -> None:
        if _is_sdxl_complete_event(dialog, event):
            if not bool(getattr(dialog, "_batikcraft_worker_event_seen", False)):
                dialog.result = None
                dialog._finish(
                    "Proses installer berhenti tanpa laporan valid. Status 100% dibatalkan.",
                    success=False,
                )
                dialog.detail.configure(
                    text=(
                        "Tidak ada event progres dari proses pengunduh. Tutup aplikasi, "
                        "pastikan mode Online aktif, lalu jalankan reparasi kembali."
                    )
                )
                return

            paths = batikbrew_runtime_model_paths(dialog.install_root)
            issues = inspect_batikbrew_runtime(paths.base_model)
            if issues:
                dialog.result = None
                details = "\n".join(f"• {issue}" for issue in issues[:10])
                remaining = len(issues) - min(len(issues), 10)
                if remaining:
                    details += f"\n• dan {remaining} masalah lain"
                dialog._finish(
                    "Instalasi belum lengkap. File SDXL yang hilang harus diunduh atau "
                    "diperbaiki sebelum BatikBrew dapat digunakan.",
                    success=False,
                )
                dialog.detail.configure(
                    text=(
                        details
                        + "\n\nPastikan mode Online aktif, lalu jalankan instalasi/reparasi lagi."
                    )
                )
                return
        original_handle_event(dialog, event)

    dialog_class._start_install = start_install  # type: ignore[assignment]
    dialog_class._enqueue_event_line = enqueue_event_line  # type: ignore[assignment]
    dialog_class._handle_event = handle_event  # type: ignore[assignment]
    dialog_class._batikcraft_completion_guard = True  # type: ignore[attr-defined]
    _INSTALLED = True


def _is_sdxl_complete_event(dialog: Any, event: object) -> bool:
    return (
        getattr(dialog, "family", "") == "sdxl"
        and isinstance(event, tuple)
        and len(event) == 2
        and event[0] == "complete"
    )


__all__ = ["install_runtime_installer_completion_guard"]
