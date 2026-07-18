"""Keep the AI cache picker on a real writable directory."""

from __future__ import annotations

from tkinter import filedialog, messagebox
from typing import Any

from batikcraft_studio.managed_storage import (
    ensure_managed_storage,
    nearest_existing_directory,
)
from batikcraft_studio.ui.ai_runtime_settings_dialog import AIRuntimeSettingsDialog

_INSTALLED = False


def install_cache_directory_guard() -> None:
    """Patch the Settings folder picker so Windows never receives a missing path."""

    global _INSTALLED
    if _INSTALLED:
        return

    dialog_class = AIRuntimeSettingsDialog
    if getattr(dialog_class, "_batikcraft_cache_directory_guard", False):
        _INSTALLED = True
        return

    def choose_cache_directory(dialog: Any) -> None:
        requested = dialog.cache_dir_value.get()
        try:
            ensure_managed_storage()
            if requested:
                requested_path = nearest_existing_directory(requested)
            else:
                requested_path = nearest_existing_directory(None)
        except OSError as exc:
            messagebox.showerror(
                "Folder cache AI tidak tersedia",
                f"BatikCraft tidak dapat menyiapkan folder cache:\n{exc}",
                parent=dialog,
            )
            requested_path = nearest_existing_directory(None)

        selected = filedialog.askdirectory(
            parent=dialog,
            initialdir=str(requested_path),
            mustexist=False,
        )
        if selected:
            dialog.cache_dir_value.set(selected)

    dialog_class.choose_cache_directory = choose_cache_directory  # type: ignore[assignment]
    dialog_class._batikcraft_cache_directory_guard = True  # type: ignore[attr-defined]
    _INSTALLED = True


__all__ = ["install_cache_directory_guard"]
