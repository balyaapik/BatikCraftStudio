from __future__ import annotations

import inspect

from batikcraft_studio.ai.batikbrew_model_settings import (
    BatikBrewLocalModelSettings,
    BatikBrewLocalModelSettingsStore,
)
from batikcraft_studio.batikbrew_context_tool_app import ContextToolApplication
from batikcraft_studio.ui import (
    batik_ai_provider_dialog,
    batikbrew_request_dialog,
    context_tool_editor_hotfix_v15,
)
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


def test_generation_requires_model_selection_after_output_mode() -> None:
    method = (
        context_tool_editor_hotfix_v15.ContextToolEditorWorkspaceView
        .batify_selected_with_pretrained_ai
    )
    flow = inspect.getsource(method)
    assert "BatikBrewOutputModeDialog" in flow
    assert "BatikAIProviderDialog" in flow
    assert "BatikBrewRequestDialog" not in flow
    assert flow.index("BatikBrewOutputModeDialog") < flow.index("BatikAIProviderDialog")
    assert "provider_id = model_dialog.result" in flow


def test_model_dialog_uses_models_saved_in_settings_without_editing_them() -> None:
    source = inspect.getsource(batik_ai_provider_dialog)
    assert 'self.title("Pilih Model Generasi AI")' in source
    assert "settings.model_for(provider_id)" in source
    assert "get_batikbrew_model_settings_store" in source
    assert "CloudAISettingsDialog" not in source
    assert "self.settings_store.save" not in source


def test_request_dialog_contains_only_creative_controls() -> None:
    source = inspect.getsource(batikbrew_request_dialog)
    assert "model_value" not in source
    assert "lora_path" not in source
    assert "API key" not in source
    assert "Creative direction" in source
    assert "Jumlah variasi" in source


def test_cloud_generation_defaults_to_one_api_request() -> None:
    request_source = inspect.getsource(batikbrew_request_dialog)
    editor_source = inspect.getsource(context_tool_editor_hotfix_v15)

    assert "default_variation_count: int = 1" in request_source
    assert "default_variation_count=1 if cloud_request else 4" in editor_source
    assert "Setiap variasi cloud mengirim satu request gambar terpisah" in editor_source
    assert "mencegah error 429 Too Many Requests" in editor_source


def test_application_exposes_settings_menu_as_ai_configuration_home() -> None:
    source = inspect.getsource(ContextToolApplication)
    assert '_insert_before_help(menu_bar, "Settings", settings_menu)' in source
    assert "Provider Cloud & Model API" in source
    assert "Model Lokal Aktif, Runtime & LoRA" in source
    assert "Runtime AI & GPU" in source
