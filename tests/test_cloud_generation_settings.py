from __future__ import annotations

import json

from batikcraft_studio.ai.generation_providers import (
    CloudGenerationSettings,
    CloudGenerationSettingsStore,
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
    PROVIDER_WATSONX,
)
from batikcraft_studio.ai.hybrid_batik_generation import CloudBatikBrewOptions


def test_cloud_settings_roundtrip_keeps_mode_defaults_and_no_secrets(tmp_path) -> None:
    path = tmp_path / "cloud_generation.json"
    store = CloudGenerationSettingsStore(path)
    settings = CloudGenerationSettings(
        ornament_provider=PROVIDER_OPENAI,
        pattern_provider=PROVIDER_GEMINI,
        openai_model="gpt-image-1",
        gemini_model="gemini-3.1-flash-image",
        watsonx_project_id="project-123",
    )

    store.save(settings)
    loaded = store.load()

    assert loaded == settings
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "api_key" not in json.dumps(payload).casefold()
    assert loaded.provider_for_mode("ornament") == PROVIDER_OPENAI
    assert loaded.provider_for_mode("pattern") == PROVIDER_GEMINI


def test_cloud_options_do_not_require_a_local_lora_file() -> None:
    options = CloudBatikBrewOptions(
        generation_provider=PROVIDER_WATSONX,
        provider_model="stable-diffusion-xl-1024-v1-0",
        output_mode="ornament",
        prompt="single leaf transformed into Indonesian Batik ornament",
        variation_count=2,
        tileable=True,
        lora_path="",
    )

    assert options.lora_path == ""
    assert options.lora_weight == 0.0
    assert options.tileable is False
    assert options.output_mode == "ornament"
    assert options.to_properties()["api_key_stored_in_project"] is False
