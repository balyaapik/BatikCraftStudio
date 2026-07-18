from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

from batikcraft_studio import __main__
from batikcraft_studio.ai import (
    batikbrew_generation,
    sdxl_online_component_repair,
    sdxl_text_component_repair,
)
from batikcraft_studio.ai.runtime_settings import AIRuntimeSettings


class _Store:
    def __init__(self, settings: AIRuntimeSettings) -> None:
        self.settings = settings
        self.saved: AIRuntimeSettings | None = None

    def load(self) -> AIRuntimeSettings:
        return self.settings

    def save(self, settings: AIRuntimeSettings) -> None:
        self.saved = settings
        self.settings = settings


def _clear_offline_environment(monkeypatch: Any) -> None:
    for name in sdxl_online_component_repair._OFFLINE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_hidden_local_only_setting_is_migrated_without_ui_toggle(monkeypatch: Any) -> None:
    _clear_offline_environment(monkeypatch)
    store = _Store(AIRuntimeSettings(local_files_only=True))
    monkeypatch.setattr(sdxl_online_component_repair, "get_ai_runtime_store", lambda: store)

    sdxl_online_component_repair._migrate_hidden_local_only_setting()

    assert store.saved is not None
    assert store.saved.local_files_only is False


def test_explicit_offline_environment_is_respected(monkeypatch: Any) -> None:
    store = _Store(AIRuntimeSettings(local_files_only=True))
    monkeypatch.setattr(sdxl_online_component_repair, "get_ai_runtime_store", lambda: store)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")

    sdxl_online_component_repair._migrate_hidden_local_only_setting()

    assert store.saved is None
    assert store.settings.local_files_only is True


def test_canonical_sdxl_repair_can_download_despite_legacy_hidden_flag(
    monkeypatch: Any,
) -> None:
    _clear_offline_environment(monkeypatch)
    calls: list[tuple[str, bool]] = []

    def original_loader(
        name: str,
        source: str,
        _subfolder: str,
        settings: Any,
        _dtype: Any,
    ) -> object:
        calls.append((source, bool(settings.local_files_only)))
        return object()

    def original_factory(settings: Any) -> tuple[Any, Any, str]:
        return settings, object(), "cpu"

    monkeypatch.setattr(
        sdxl_text_component_repair,
        "_load_transformers_component",
        original_loader,
    )
    monkeypatch.setattr(
        batikbrew_generation,
        "_default_sdxl_pipeline_factory",
        original_factory,
    )
    monkeypatch.setattr(sdxl_online_component_repair, "_INSTALLED", False)
    monkeypatch.setattr(
        sdxl_online_component_repair,
        "_migrate_hidden_local_only_setting",
        lambda: None,
    )

    sdxl_online_component_repair.install_sdxl_online_component_repair()
    settings = SimpleNamespace(
        model_id_or_path="local-model",
        local_files_only=True,
        cache_dir=None,
    )
    sdxl_text_component_repair._load_transformers_component(
        "tokenizer_2",
        batikbrew_generation.SDXL_BASE_MODEL_ID,
        "tokenizer_2",
        settings,
        None,
    )

    assert calls == [(batikbrew_generation.SDXL_BASE_MODEL_ID, False)]
    message = sdxl_text_component_repair._missing_component_message(
        settings,
        ["tokenizer_2", "text_encoder_2"],
    )
    assert "local-files-only" not in message
    assert "internet" in message.casefold()
    assert "pemulih" in message.casefold()


def test_startup_installs_online_repair_before_lora_restore() -> None:
    source = inspect.getsource(__main__.main)

    assert "install_sdxl_online_component_repair" in source
    assert source.index("install_sdxl_online_component_repair()") < source.index(
        "install_lora_activation_persistence()"
    )
