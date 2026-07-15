"""AI background dialog adapter that consumes the global GPU/runtime profile."""

from __future__ import annotations

from batikcraft_studio.ai.global_runtime import (
    apply_global_runtime_to_background_options,
)
from batikcraft_studio.ai.runtime_settings import load_ai_runtime_settings

from .ai_batik_background_dialog import AIBatikBackgroundDialog as _BaseDialog


class GlobalAIBatikBackgroundDialog(_BaseDialog):
    """Keep creative controls local while compute controls remain global."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        runtime = load_ai_runtime_settings()
        self.model_value.set(runtime.default_model)
        self.runtime_banner = self._runtime_banner(runtime)
        self.status_value.set(
            f"{self.runtime_banner} Atur prompt lalu klik Generate Preview."
        )

    def collect_options(self):  # type: ignore[no-untyped-def]
        options = super().collect_options()
        return apply_global_runtime_to_background_options(options)

    def _show_result(self, preview):  # type: ignore[no-untyped-def]
        super()._show_result(preview)
        device = preview.result.metadata.get("device", "-")
        precision = preview.options.precision
        self.runtime_banner = f"Runtime aktual: {device} · {precision}"

    @staticmethod
    def _runtime_banner(runtime) -> str:  # type: ignore[no-untyped-def]
        offload = "on" if runtime.effective_cpu_offload else "off"
        return (
            f"Runtime global: {runtime.device} · {runtime.precision} · "
            f"CPU offload {offload}."
        )


__all__ = ["GlobalAIBatikBackgroundDialog"]
