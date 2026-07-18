"""Prevent the runtime installer dialog from displaying false success.

The actual download runs in a child process.  Even though the child now performs
strict SDXL validation, the GUI also validates the target folder before turning
the progress bar into 100%.  This protects against stale events, older workers,
and interrupted downloads that accidentally return exit code zero.
"""

from __future__ import annotations

from typing import Any

from batikcraft_studio.ai.runtime_model_installer import batikbrew_runtime_model_paths
from batikcraft_studio.ai.sdxl_runtime_integrity import inspect_batikbrew_runtime
from batikcraft_studio.ui.ai_runtime_model_install_dialog import RuntimeModelInstallDialog

_INSTALLED = False


def install_runtime_installer_completion_guard() -> None:
    """Validate the exact SDXL folder before the dialog announces success."""

    global _INSTALLED
    if _INSTALLED:
        return

    dialog_class = RuntimeModelInstallDialog
    if getattr(dialog_class, "_batikcraft_completion_guard", False):
        _INSTALLED = True
        return

    original_handle_event = dialog_class._handle_event

    def handle_event(dialog: Any, event: object) -> None:
        if _is_sdxl_complete_event(dialog, event):
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
