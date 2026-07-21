"""Allow mandatory SDXL text-component repair without a hidden UI toggle.

Older BatikCraft builds persisted ``local_files_only`` in ``ai_runtime.json`` but
never exposed that value in the Settings UI.  A user could therefore be told to
turn off a switch that did not exist while BatikBrew refused to download the
mandatory SDXL ``tokenizer_2`` and ``text_encoder_2`` components.

This compatibility policy migrates that hidden legacy value back to the normal
online-capable default and permits the canonical SDXL Base fallback to download
only the missing text components.  Explicit Hugging Face/Transformers offline
environment variables are still respected.
"""

from __future__ import annotations

import logging
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from batikcraft_studio.ai import batikbrew_generation, sdxl_text_component_repair
from batikcraft_studio.ai.runtime_settings import get_ai_runtime_store

_LOGGER = logging.getLogger(__name__)
_INSTALLED = False
_OFFLINE_ENV_NAMES = (
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
    "DIFFUSERS_OFFLINE",
)


class _SettingsOverride:
    """Read-through settings view with selected attribute overrides."""

    def __init__(self, original: Any, **overrides: object) -> None:
        self._original = original
        self._overrides = overrides

    def __getattr__(self, name: str) -> Any:
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._original, name)


def install_sdxl_online_component_repair() -> None:
    """Install automatic online repair after the base repair module."""

    global _INSTALLED
    if _INSTALLED:
        return

    _migrate_hidden_local_only_setting()

    original_loader = sdxl_text_component_repair._load_transformers_component
    original_factory = batikbrew_generation._default_sdxl_pipeline_factory

    def online_component_loader(
        name: str,
        source: str,
        subfolder: str,
        settings: Any,
        dtype: Any,
    ) -> Any:
        effective = settings
        if (
            source == batikbrew_generation.SDXL_BASE_MODEL_ID
            and bool(getattr(settings, "local_files_only", False))
            and not _explicit_offline_environment()
        ):
            effective = _SettingsOverride(settings, local_files_only=False)
            _LOGGER.info(
                "Memulihkan komponen SDXL %s dari repository/cache resmi.",
                name,
            )
        return original_loader(name, source, subfolder, effective, dtype)

    def online_capable_factory(settings: Any) -> tuple[Any, Any, str]:
        source = str(getattr(settings, "model_id_or_path", "")).strip()
        local_source = Path(source).expanduser()
        effective = settings
        if (
            source
            and not local_source.exists()
            and bool(getattr(settings, "local_files_only", False))
            and not _explicit_offline_environment()
        ):
            effective = _SettingsOverride(settings, local_files_only=False)
        return original_factory(effective)

    def actionable_message(settings: Any, missing: list[str]) -> str:
        labels = ", ".join(missing) if missing else "tokenizer_2, text_encoder_2"
        if _explicit_offline_environment():
            hint = (
                "Mode offline eksplisit dari environment sedang aktif. Hapus "
                "HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE/DIFFUSERS_OFFLINE atau pilih "
                "folder Diffusers SDXL lengkap."
            )
        else:
            hint = (
                "BatikCraft sudah mencoba memulihkannya otomatis dari SDXL Base. "
                "Pastikan internet dapat mengakses Hugging Face, lalu coba lagi, "
                "atau pilih folder Diffusers SDXL lengkap."
            )
        return (
            f"Base model SDXL tidak lengkap: komponen {labels} tidak tersedia. "
            "Folder model harus memiliki tokenizer_2 dan text_encoder_2. "
            + hint
        )

    sdxl_text_component_repair._load_transformers_component = online_component_loader
    sdxl_text_component_repair._missing_component_message = actionable_message
    batikbrew_generation._default_sdxl_pipeline_factory = online_capable_factory
    _INSTALLED = True


def _migrate_hidden_local_only_setting() -> None:
    """Disable the legacy hidden flag unless offline mode was explicitly requested."""

    if _explicit_offline_environment():
        return
    store = get_ai_runtime_store()
    settings = store.load()
    if not settings.local_files_only:
        return
    try:
        store.save(replace(settings, local_files_only=False))
    except OSError as exc:
        _LOGGER.warning("Gagal memigrasikan local_files_only tersembunyi: %s", exc)
    else:
        _LOGGER.info(
            "Pengaturan local_files_only tersembunyi dimigrasikan ke nilai default false."
        )


def _explicit_offline_environment() -> bool:
    """True hanya bila PENGGUNA yang meminta mode offline lewat environment.

    Nilai yang dipasang aplikasi saat memuat runtime LoRA lokal tidak dihitung;
    kalau dihitung, reparasi komponen SDXL akan menolak mengunduh padahal
    pengguna sudah mencentang 'Izinkan Download & Reparasi Model (Online)'.
    """

    try:
        from batikcraft_studio.ai.offline_runtime import app_applied_offline_names

        applied = app_applied_offline_names()
    except Exception:  # noqa: BLE001
        applied = frozenset()
    return any(
        name not in applied and _truthy_environment(os.environ.get(name))
        for name in _OFFLINE_ENV_NAMES
    )


def _truthy_environment(value: str | None) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


__all__ = ["install_sdxl_online_component_repair"]
