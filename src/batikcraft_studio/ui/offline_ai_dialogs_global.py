"""Offline LoRA manager adapter that respects the global AI/GPU profile."""

from __future__ import annotations

from dataclasses import replace
from tkinter import messagebox, ttk

from batikcraft_studio.ai.runtime_model_installer import find_installed_runtime_models
from batikcraft_studio.ai.runtime_settings import (
    get_ai_runtime_store,
    load_ai_runtime_settings,
)

from .ai_runtime_model_install_dialog import RuntimeModelInstallDialog
from .offline_ai_dialogs import OfflineModelManagerWindow as _BaseOfflineModelManagerWindow


class GlobalOfflineModelManagerWindow(_BaseOfflineModelManagerWindow):
    """Use managed local model paths and the compute choices from Preferences."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._add_runtime_installer_button()
        self._autofill_managed_runtime()
        self._sync_global_runtime_controls()
        self.title(f"{self.title()} — runtime dari Preferences AI & GPU")

    def _activate(self) -> None:
        self._sync_global_runtime_controls()
        super()._activate()

    def _sync_global_runtime_controls(self) -> None:
        runtime = load_ai_runtime_settings()
        self.device_value.set(runtime.device)
        self.precision_value.set(runtime.precision)
        self.cpu_offload.set(runtime.effective_cpu_offload)

    def _add_runtime_installer_button(self) -> None:
        bottom = self.status.master
        self.runtime_installer_button = ttk.Button(
            bottom,
            text="Unduh & Instal Runtime AI…",
            command=self._install_managed_runtime,
        )
        self.runtime_installer_button.pack(side="right", padx=(0, 6))

    def _autofill_managed_runtime(self) -> None:
        paths = find_installed_runtime_models()
        if paths is None:
            return
        self.base_path.set(str(paths.base_model))
        self.controlnet_path.set(str(paths.controlnet))

    def _install_managed_runtime(self) -> None:
        dialog = RuntimeModelInstallDialog(self)
        self.wait_window(dialog)
        paths = dialog.result
        if paths is None:
            return

        self.base_path.set(str(paths.base_model))
        self.controlnet_path.set(str(paths.controlnet))

        try:
            store = get_ai_runtime_store()
            current = store.load()
            store.save(
                replace(
                    current,
                    default_model=str(paths.base_model),
                    local_files_only=True,
                )
            )
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showwarning(
                self.title(),
                "Model berhasil dipasang, tetapi pengaturan AI global tidak dapat "
                f"disimpan: {exc}",
                parent=self,
            )
        else:
            self.status.configure(
                text="Runtime AI lokal siap. Pilih LoRA lalu tekan Aktifkan Model."
            )
            self._changed()


__all__ = ["GlobalOfflineModelManagerWindow"]
