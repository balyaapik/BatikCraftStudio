"""Offline LoRA manager adapter for global SD1.5 and BatikBrew SDXL runtimes."""

from __future__ import annotations

from dataclasses import replace
from tkinter import messagebox, ttk

from batikcraft_studio.ai.batikbrew_model_settings import (
    BatikBrewLocalModelSettings,
    get_batikbrew_model_settings_store,
)
from batikcraft_studio.ai.runtime_model_installer import (
    BatikBrewRuntimePaths,
    find_installed_batikbrew_runtime,
    find_installed_runtime_models,
)
from batikcraft_studio.ai.runtime_settings import (
    get_ai_runtime_store,
    load_ai_runtime_settings,
)

from .ai_runtime_model_install_dialog import RuntimeModelInstallDialog
from .offline_ai_dialogs import OfflineModelManagerWindow as _BaseOfflineModelManagerWindow


class GlobalOfflineModelManagerWindow(_BaseOfflineModelManagerWindow):
    """Manage and persist the one local model profile used by generation."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._add_runtime_installer_buttons()
        self._autofill_managed_runtime()
        self._sync_global_runtime_controls()
        self.title(f"{self.title()} — Settings AI, Model & LoRA")
        self._refresh()

    def _refresh(self) -> None:
        super()._refresh()
        active = get_batikbrew_model_settings_store().load()
        if active.configured and self.tree.exists(active.model_id):
            self.tree.selection_set(active.model_id)
            self.tree.see(active.model_id)
            self.status.configure(
                text=f"Model aktif untuk BatikBrew: {active.model_id} · {active.resolution}px."
            )

    def _activate(self) -> None:
        model_id = self._selected_model_id()
        if model_id is not None:
            try:
                model = self.session.model_library.get(model_id)
            except Exception:  # noqa: BLE001 - base class shows normalized errors
                model = None
            if model is not None and "sdxl" in model.manifest.base_model_family.casefold():
                self._activate_batikbrew_model(model_id)
                return
        self._sync_global_runtime_controls()
        super()._activate()

    def _activate_batikbrew_model(self, model_id: str) -> None:
        paths = find_installed_batikbrew_runtime()
        if paths is None:
            messagebox.showerror(
                self.title(),
                "Model ini memakai SDXL. Tekan 'Instal BatikBrew SDXL…' terlebih dahulu.",
                parent=self,
            )
            return
        try:
            model = self.session.model_library.get(model_id)
            runtime_store = get_ai_runtime_store()
            current = runtime_store.load()
            runtime_store.save(
                replace(
                    current,
                    default_model=str(paths.base_model),
                    local_files_only=True,
                )
            )
            resolution = min(1024, max(512, int(model.manifest.resolution)))
            supported = min((512, 640, 768, 896, 1024), key=lambda value: abs(value - resolution))
            get_batikbrew_model_settings_store().save(
                BatikBrewLocalModelSettings(
                    model_id=model.model_id,
                    base_model_path=str(paths.base_model),
                    lora_path=str(model.lora_path),
                    lora_weight=float(self.lora_value.get()),
                    trigger_words=tuple(model.manifest.trigger_words) or ("batikbrew",),
                    inference_steps=max(10, int(self.steps_value.get())),
                    guidance_scale=max(1.0, float(self.guidance_value.get())),
                    resolution=supported,
                )
            )
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self.tree.selection_set(model_id)
        self.status.configure(
            text=(
                f"Model SDXL {model_id} disimpan sebagai model BatikBrew aktif. "
                "Generasi berikutnya akan memakainya otomatis."
            )
        )
        self._changed()

    def _uninstall(self) -> None:
        model_id = self._selected_model_id()
        super()._uninstall()
        if model_id is None or self.tree.exists(model_id):
            return
        store = get_batikbrew_model_settings_store()
        if store.load().model_id == model_id:
            try:
                store.clear()
            except OSError as exc:
                messagebox.showwarning(self.title(), str(exc), parent=self)
            else:
                self.status.configure(text="Model BatikBrew aktif dihapus. Pilih model lain.")

    def _sync_global_runtime_controls(self) -> None:
        runtime = load_ai_runtime_settings()
        self.device_value.set(runtime.device)
        self.precision_value.set(runtime.precision)
        self.cpu_offload.set(runtime.effective_cpu_offload)

    def _add_runtime_installer_buttons(self) -> None:
        bottom = self.status.master
        self.runtime_installer_button = ttk.Button(
            bottom,
            text="Instal Runtime SD1.5…",
            command=self._install_managed_runtime,
        )
        self.runtime_installer_button.pack(side="right", padx=(0, 6))
        self.batikbrew_runtime_button = ttk.Button(
            bottom,
            text="Instal BatikBrew SDXL…",
            command=self._install_batikbrew_runtime,
        )
        self.batikbrew_runtime_button.pack(side="right", padx=(0, 6))

    def _autofill_managed_runtime(self) -> None:
        paths = find_installed_runtime_models()
        if paths is None:
            return
        self.base_path.set(str(paths.base_model))
        self.controlnet_path.set(str(paths.controlnet))

    def _install_managed_runtime(self) -> None:
        dialog = RuntimeModelInstallDialog(self, family="sd15")
        self.wait_window(dialog)
        paths = dialog.result
        if paths is None or isinstance(paths, BatikBrewRuntimePaths):
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
                text="Runtime SD1.5 lokal siap untuk workflow legacy dan ControlNet."
            )
            self._changed()

    def _install_batikbrew_runtime(self) -> None:
        dialog = RuntimeModelInstallDialog(self, family="sdxl")
        self.wait_window(dialog)
        paths = dialog.result
        if not isinstance(paths, BatikBrewRuntimePaths):
            return
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
                "SDXL berhasil dipasang, tetapi pengaturan global gagal disimpan: "
                f"{exc}",
                parent=self,
            )
            return
        self.status.configure(
            text=(
                "Runtime BatikBrew SDXL siap. Pilih paket LoRA SDXL lalu tekan "
                "Aktifkan Model untuk menjadikannya default."
            )
        )
        self._changed()


__all__ = ["GlobalOfflineModelManagerWindow"]
