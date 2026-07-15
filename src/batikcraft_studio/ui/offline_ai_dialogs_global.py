"""Offline LoRA manager adapter that respects the global AI/GPU profile."""

from __future__ import annotations

from batikcraft_studio.ai.runtime_settings import load_ai_runtime_settings

from .offline_ai_dialogs import OfflineModelManagerWindow as _BaseOfflineModelManagerWindow


class GlobalOfflineModelManagerWindow(_BaseOfflineModelManagerWindow):
    """Use local model paths here, but take compute choices from Preferences."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
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


__all__ = ["GlobalOfflineModelManagerWindow"]
