from __future__ import annotations

import inspect

from batikcraft_studio.ai.batikbrew_model_settings import (
    BatikBrewLocalModelSettings,
    BatikBrewLocalModelSettingsStore,
)
from batikcraft_studio.batikbrew_context_tool_app import ContextToolApplication
from batikcraft_studio.ui import batikbrew_request_dialog
from batikcraft_studio.ui import context_tool_editor_hotfix_v15
from batikcraft_studio.ui.views import ContextToolEditorWorkspaceView


def test_local_batikbrew_model_profile_round_trip(tmp_path) -> None:
    store = BatikBrewLocalModelSettingsStore(tmp_path / "batikbrew-model.json")
    settings = BatikBrewLocalModelSettings(
        model_id="batikbrew-sogan-v1",
        base_model_path="D:/models/sdxl",
        lora_path="D:/models/batikbrew.safetensors",
        lora_weight=0.9,
        trigger_words=("batikbrew", "sogan"),
        inference_steps=36,
        guidance_scale=7.5,
        resolution=1024,
    )

    store.save(settings)
    loaded = store.load()

    assert loaded == settings
    assert loaded.configured is True
    store.clear()
    assert store.load().configured is False


def test_active_editor_uses_centralized_settings_hotfix() -> None:
    assert ContextToolEditorWorkspaceView.__module__.endswith(
        "context_tool_editor_hotfix_v15"
    )


def test_generation_flow_does_not_open_provider_or_model_settings() -> None:
    source = inspect.getsource(context_tool_editor_hotfix_v15)
    assert "BatikAIProviderDialog" not in source
    assert "CloudBatikGenerationDialog" not in source
    assert "BatikBrewGenerationDialog" not in source
    assert "provider_for_mode" in source
    assert "get_batikbrew_model_settings_store" in source


def test_request_dialog_contains_only_creative_controls() -> None:
    source = inspect.getsource(batikbrew_request_dialog)
    assert "model_value" not in source
    assert "lora_path" not in source
    assert "API key" not in source
    assert "Creative direction" in source
    assert "Jumlah variasi" in source


def test_application_exposes_settings_menu_as_ai_configuration_home() -> None:
    source = inspect.getsource(ContextToolApplication)
    assert 'label="Settings"' in source
    assert "Provider Cloud & Model API" in source
    assert "Model Lokal, Runtime & LoRA" in source
    assert "Runtime AI & GPU" in source
