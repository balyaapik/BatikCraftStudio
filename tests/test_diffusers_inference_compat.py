from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from batikcraft_studio import __main__
from batikcraft_studio.ai.diffusers_inference_compat import (
    _install_clip_prompt_guard,
    _is_unet_only_lora,
    _load_lora_adapter,
    _priority_batik_prompt,
    configure_pipeline_memory_features_compat,
)


class _FakeVae:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def enable_slicing(self) -> None:
        self.calls.append("enable_slicing")

    def disable_slicing(self) -> None:
        self.calls.append("disable_slicing")

    def enable_tiling(self) -> None:
        self.calls.append("enable_tiling")

    def disable_tiling(self) -> None:
        self.calls.append("disable_tiling")


class _MemoryPipeline:
    def __init__(self) -> None:
        self.vae = _FakeVae()
        self.calls: list[str] = []

    def enable_attention_slicing(self) -> None:
        self.calls.append("enable_attention_slicing")

    def disable_attention_slicing(self) -> None:
        self.calls.append("disable_attention_slicing")

    def enable_vae_slicing(self) -> None:
        raise AssertionError("deprecated pipeline VAE slicing API was called")

    def disable_vae_slicing(self) -> None:
        raise AssertionError("deprecated pipeline VAE slicing API was called")

    def enable_vae_tiling(self) -> None:
        raise AssertionError("deprecated pipeline VAE tiling API was called")

    def disable_vae_tiling(self) -> None:
        raise AssertionError("deprecated pipeline VAE tiling API was called")


def test_vae_memory_features_use_component_level_diffusers_api() -> None:
    pipeline = _MemoryPipeline()
    runtime = SimpleNamespace(
        effective_attention_slicing=True,
        effective_vae_slicing=True,
        effective_vae_tiling=False,
    )

    configure_pipeline_memory_features_compat(pipeline, runtime)

    assert pipeline.calls == ["enable_attention_slicing"]
    assert pipeline.vae.calls == ["enable_slicing", "disable_tiling"]


class _UnetOnlyPipeline:
    def __init__(self) -> None:
        self.unet = object()
        self.loaded_unet: tuple[dict[str, object], str] | None = None
        self.adapters: tuple[list[str], list[float]] | None = None

    def lora_state_dict(
        self,
        _directory: str,
        *,
        weight_name: str,
    ) -> tuple[dict[str, object], dict[str, float]]:
        assert weight_name.endswith(".safetensors")
        return (
            {"unet.down_blocks.0.attentions.0.to_q.lora_A.weight": object()},
            {"unet.down_blocks.0.attentions.0.to_q.alpha": 8.0},
        )

    def load_lora_into_unet(
        self,
        state_dict: dict[str, object],
        _network_alphas: dict[str, float],
        _unet: object,
        *,
        adapter_name: str,
        _pipeline: Any | None = None,
    ) -> None:
        assert _pipeline is self
        self.loaded_unet = (state_dict, adapter_name)

    def load_lora_weights(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("pipeline-wide LoRA loader should not inspect text encoders")

    def set_adapters(
        self,
        names: list[str],
        *,
        adapter_weights: list[float],
    ) -> None:
        self.adapters = (names, adapter_weights)


def test_unet_only_safetensors_skips_missing_text_encoder_probes(
    tmp_path: Path,
) -> None:
    weights = tmp_path / "batikcraft-unet.safetensors"
    weights.write_bytes(b"placeholder")
    pipeline = _UnetOnlyPipeline()

    loaded_component = _load_lora_adapter(
        pipeline,
        weights,
        adapter_name="batikbrew",
        adapter_weight=0.83,
    )

    assert loaded_component == "unet"
    assert pipeline.loaded_unet is not None
    assert pipeline.loaded_unet[1] == "batikbrew"
    assert pipeline.adapters == (["batikbrew"], [0.83])


def test_direct_peft_unet_keys_are_recognized_without_unet_prefix() -> None:
    assert _is_unet_only_lora(
        {
            "base_model.model.down_blocks.0.attentions.0.to_q.lora_A.weight": object(),
            "base_model.model.down_blocks.0.attentions.0.to_q.lora_B.weight": object(),
        }
    ) is True
    assert _is_unet_only_lora(
        {
            "unet.down_blocks.0.attentions.0.to_q.lora_A.weight": object(),
            "text_encoder.text_model.encoder.layers.0.self_attn.q_proj.lora_A.weight": object(),
        }
    ) is False


class _WordTokenizer:
    model_max_length = 20

    def tokenize(self, text: str) -> list[str]:
        return text.replace(",", " , ").split()


class _PromptPipeline:
    def __init__(self) -> None:
        self.tokenizer = _WordTokenizer()
        self.tokenizer_2 = _WordTokenizer()
        self.received: dict[str, object] = {}

    def encode_prompt(
        self,
        prompt: str | None = None,
        prompt_2: str | None = None,
        negative_prompt: str | None = None,
        negative_prompt_2: str | None = None,
    ) -> dict[str, object]:
        self.received = {
            "prompt": prompt,
            "prompt_2": prompt_2,
            "negative_prompt": negative_prompt,
            "negative_prompt_2": negative_prompt_2,
        }
        return self.received


def test_clip_prompt_guard_prioritizes_direction_and_stays_inside_context() -> None:
    analysis = SimpleNamespace(
        palette_names=("sogan brown", "cream", "indigo"),
        theme_keywords=("kawung ornament", "floral ornament"),
        style_hints=("classical parang motif",),
        composition_hint="dense intricate ornament with fine lines",
    )
    prompt = _priority_batik_prompt(
        analysis,
        custom_direction=(
            "authentic Indonesian batik ornament, intricate decorative details, "
            "preserve exact object silhouette"
        ),
        trigger_words=("batikbrew",),
    )
    pipeline = _PromptPipeline()
    _install_clip_prompt_guard(pipeline)

    result = pipeline.encode_prompt(
        prompt=prompt,
        prompt_2=prompt,
        negative_prompt=(
            "blurry, low quality, watermark, text, photograph, collage, "
            "photorealistic, distorted, extra objects"
        ),
    )

    actual = str(result["prompt"])
    assert "batikbrew" in actual
    assert "preserve" in actual
    assert "silhouette" in actual
    assert len(pipeline.tokenizer.tokenize(actual)) <= 18
    assert len(pipeline.tokenizer_2.tokenize(actual)) <= 18
    assert len(pipeline.tokenizer.tokenize(str(result["negative_prompt"]))) <= 18


def test_startup_installs_diffusers_fix_before_lora_session_restore() -> None:
    source = inspect.getsource(__main__.main)

    assert "install_diffusers_inference_compatibility" in source
    assert source.index("install_diffusers_inference_compatibility()") < source.index(
        "install_lora_activation_persistence()"
    )
