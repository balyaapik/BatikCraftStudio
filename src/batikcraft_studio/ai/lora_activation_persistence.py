"""Persist and restore the LoRA model activated from the offline model manager.

The model manager historically changed only the in-memory
``OfflineAIProjectSession`` provider. BatikBrew generation, however, reads the
central ``batikbrew_model.json`` profile. This bridge keeps both paths in sync:
activating an installed ``.safetensors`` LoRA writes the central profile,
foundation mode clears it, and a new application session restores the active
provider from disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from batikcraft_studio.ai.batikbrew_model_settings import (
    BatikBrewLocalModelSettings,
    BatikBrewLocalModelSettingsStore,
    get_batikbrew_model_settings_store,
)
from batikcraft_studio.ai.runtime_settings import load_ai_runtime_settings
from batikcraft_studio.application.offline_ai_session import OfflineAIProjectSession
from batikcraft_studio.application.session import ProjectSessionError

_INSTALLED = False
_SUPPORTED_RESOLUTIONS = (512, 640, 768, 896, 1024)


def install_lora_activation_persistence() -> None:
    """Install the active-LoRA persistence bridge once per process."""

    global _INSTALLED
    if _INSTALLED:
        return

    cls = OfflineAIProjectSession
    original_init = cls.__init__
    original_configure = cls.configure_offline_model
    original_foundation = cls.use_foundation_renderer

    def persistent_init(
        self: OfflineAIProjectSession,
        *args: object,
        **kwargs: object,
    ) -> None:
        settings_store = kwargs.pop("model_settings_store", None)
        original_init(self, *args, **kwargs)
        self._active_lora_settings_store = (
            settings_store
            if isinstance(settings_store, BatikBrewLocalModelSettingsStore)
            else get_batikbrew_model_settings_store()
        )
        self._active_lora_restore_error: str | None = None
        _restore_active_model(self, original_configure, original_foundation)

    def persistent_configure(
        self: OfflineAIProjectSession,
        model_id: str,
        **kwargs: Any,
    ) -> Any:
        selection = original_configure(self, model_id, **kwargs)
        model = self.model_library.get(model_id)
        lora_scale = kwargs.get("lora_scale")
        active = BatikBrewLocalModelSettings(
            model_id=model.model_id,
            base_model_path=str(selection.base_model_path),
            lora_path=str(model.lora_path.resolve()),
            lora_weight=(
                model.manifest.recommended_weight
                if lora_scale is None
                else float(lora_scale)
            ),
            trigger_words=model.manifest.trigger_words,
            inference_steps=int(kwargs.get("inference_steps", 28)),
            guidance_scale=float(kwargs.get("guidance_scale", 7.0)),
            resolution=_nearest_supported_resolution(model.manifest.resolution),
        )
        try:
            _settings_store(self).save(active)
        except OSError as exc:
            original_foundation(self)
            raise ProjectSessionError(
                f"Model LoRA aktif tetapi gagal disimpan ke sistem: {exc}"
            ) from exc
        self._active_lora_restore_error = None
        return selection

    def persistent_foundation(self: OfflineAIProjectSession) -> None:
        original_foundation(self)
        try:
            _settings_store(self).clear()
        except OSError as exc:
            raise ProjectSessionError(
                f"Status model LoRA gagal dinonaktifkan dari sistem: {exc}"
            ) from exc
        self._active_lora_restore_error = None

    def restore_error(self: OfflineAIProjectSession) -> str | None:
        return getattr(self, "_active_lora_restore_error", None)

    cls.__init__ = persistent_init
    cls.configure_offline_model = persistent_configure
    cls.use_foundation_renderer = persistent_foundation
    cls.active_lora_restore_error = property(restore_error)
    _INSTALLED = True


def _restore_active_model(
    session: OfflineAIProjectSession,
    original_configure: Any,
    original_foundation: Any,
) -> None:
    store = _settings_store(session)
    active = store.load()
    if store.last_error:
        session._active_lora_restore_error = store.last_error
        return
    if not active.configured:
        return

    try:
        model = session.model_library.get(active.model_id)
        if not model.lora_path.is_file():
            raise ProjectSessionError(
                f"File LoRA aktif tidak ditemukan: {model.lora_path}"
            )
        base_model = Path(active.base_model_path).expanduser()
        if not base_model.is_dir():
            raise ProjectSessionError(
                f"Folder base model aktif tidak ditemukan: {base_model}"
            )
        runtime = load_ai_runtime_settings()
        original_configure(
            session,
            model.model_id,
            base_model_path=base_model,
            controlnet_path=None,
            device=runtime.device,
            precision=runtime.precision,
            inference_steps=active.inference_steps,
            guidance_scale=active.guidance_scale,
            lora_scale=active.lora_weight,
            cpu_offload=runtime.effective_cpu_offload,
        )
    except Exception as exc:  # noqa: BLE001 - startup must remain usable
        original_foundation(session)
        session._active_lora_restore_error = (
            "Model LoRA tersimpan tidak dapat dipulihkan: " + str(exc)
        )
        return

    # Rewrite the profile with the authoritative installed weight path. This also
    # repairs stale paths left by an application move or dependency migration.
    repaired = BatikBrewLocalModelSettings(
        model_id=model.model_id,
        base_model_path=str(base_model.resolve()),
        lora_path=str(model.lora_path.resolve()),
        lora_weight=active.lora_weight,
        trigger_words=model.manifest.trigger_words,
        inference_steps=active.inference_steps,
        guidance_scale=active.guidance_scale,
        resolution=_nearest_supported_resolution(model.manifest.resolution),
    )
    try:
        store.save(repaired)
    except OSError as exc:
        session._active_lora_restore_error = (
            "Model LoRA berhasil dipulihkan tetapi profil aktif gagal diperbarui: "
            + str(exc)
        )


def _settings_store(
    session: OfflineAIProjectSession,
) -> BatikBrewLocalModelSettingsStore:
    store = getattr(session, "_active_lora_settings_store", None)
    if isinstance(store, BatikBrewLocalModelSettingsStore):
        return store
    store = get_batikbrew_model_settings_store()
    session._active_lora_settings_store = store
    return store


def _nearest_supported_resolution(value: int) -> int:
    resolution = int(value)
    return min(_SUPPORTED_RESOLUTIONS, key=lambda candidate: abs(candidate - resolution))


__all__ = ["install_lora_activation_persistence"]
