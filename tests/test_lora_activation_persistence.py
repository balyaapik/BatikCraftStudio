from __future__ import annotations

from pathlib import Path

from batikcraft_studio.ai.batikbrew_model_settings import (
    BatikBrewLocalModelSettingsStore,
)
from batikcraft_studio.ai.lora_activation_persistence import (
    install_lora_activation_persistence,
)
from batikcraft_studio.ai.model_pack import (
    BatikModelManifest,
    build_batik_model_pack,
)
from batikcraft_studio.application import OfflineAIProjectSession

install_lora_activation_persistence()


def _installed_session(
    tmp_path: Path,
) -> tuple[
    OfflineAIProjectSession,
    BatikBrewLocalModelSettingsStore,
    Path,
]:
    model_root = tmp_path / "models"
    settings_store = BatikBrewLocalModelSettingsStore(tmp_path / "batikbrew_model.json")
    base_model = tmp_path / "sdxl-base"
    base_model.mkdir()
    weights = tmp_path / "batikcraft-trained.safetensors"
    weights.write_bytes(b"safe-tensors-placeholder")
    pack = build_batik_model_pack(
        BatikModelManifest(
            model_id="batikcraft-trained",
            name="BatikCraft Trained",
            version="1.0",
            model_type="lora",
            base_model_family="sdxl",
            trigger_words=("batikcraft", "indonesian batik"),
            recommended_weight=0.82,
            resolution=1024,
            capabilities=("ornament", "pattern"),
            lora_file="ignored.safetensors",
        ),
        weights,
        tmp_path / "batikcraft-trained.batikmodel",
    )
    session = OfflineAIProjectSession(
        model_root=model_root,
        model_settings_store=settings_store,
    )
    session.install_model_pack(pack)
    return session, settings_store, base_model


def test_activating_safetensors_lora_persists_central_batikbrew_profile(
    tmp_path: Path,
) -> None:
    session, store, base_model = _installed_session(tmp_path)

    selection = session.configure_offline_model(
        "batikcraft-trained",
        base_model_path=base_model,
        device="cpu",
        precision="float32",
        inference_steps=34,
        guidance_scale=8.0,
        lora_scale=0.91,
    )

    active = store.load()
    assert active.configured is True
    assert active.model_id == "batikcraft-trained"
    assert Path(active.base_model_path) == base_model.resolve()
    assert Path(active.lora_path).is_file()
    assert Path(active.lora_path).suffix == ".safetensors"
    assert active.lora_weight == 0.91
    assert active.trigger_words == ("batikcraft", "indonesian batik")
    assert active.inference_steps == 34
    assert active.guidance_scale == 8.0
    assert active.resolution == 1024
    assert selection.model_id == active.model_id


def test_new_session_restores_active_lora_and_foundation_clears_it(
    tmp_path: Path,
) -> None:
    session, store, base_model = _installed_session(tmp_path)
    session.configure_offline_model(
        "batikcraft-trained",
        base_model_path=base_model,
        device="cpu",
        precision="float32",
        lora_scale=0.87,
    )

    restored = OfflineAIProjectSession(
        model_root=tmp_path / "models",
        model_settings_store=store,
    )

    assert restored.runtime_selection is not None
    assert restored.runtime_selection.model_id == "batikcraft-trained"
    assert restored.batification_provider_id == "offline-lora:batikcraft-trained"
    assert restored.active_lora_restore_error is None

    restored.use_foundation_renderer()

    assert restored.runtime_selection is None
    assert store.load().configured is False
