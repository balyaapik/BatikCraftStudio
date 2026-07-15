"""Adapters that apply global AI/GPU settings to every inference provider."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from batikcraft_studio.ai.pretrained_background import (
    AIBatikBackgroundOptions,
    PretrainedBatikBackgroundProvider,
)
from batikcraft_studio.ai.pretrained_batification import (
    PretrainedAIBatificationOptions,
    PretrainedImg2ImgBatificationProvider,
)
from batikcraft_studio.ai.runtime_settings import (
    AIRuntimeSettings,
    load_ai_runtime_settings,
)


def apply_global_runtime_to_background_options(
    options: AIBatikBackgroundOptions,
    settings: AIRuntimeSettings | None = None,
) -> AIBatikBackgroundOptions:
    """Keep creative controls local while forcing compute controls to global values."""

    runtime = settings or load_ai_runtime_settings()
    return replace(
        options,
        device=runtime.device,
        precision=runtime.precision,
        local_files_only=runtime.local_files_only,
        cpu_offload=runtime.effective_cpu_offload,
        cache_dir=runtime.cache_dir,
    )


def pretrained_batification_options_from_global(
    settings: AIRuntimeSettings | None = None,
) -> PretrainedAIBatificationOptions:
    """Build object-Batification settings from the current global runtime profile."""

    runtime = settings or load_ai_runtime_settings()
    defaults = PretrainedAIBatificationOptions()
    return replace(
        defaults,
        model_id_or_path=runtime.default_model,
        device=runtime.device,
        precision=runtime.precision,
        local_files_only=runtime.local_files_only,
        cpu_offload=runtime.effective_cpu_offload,
        cache_dir=runtime.cache_dir,
    )


def configure_pipeline_memory_features(
    pipeline: Any,
    settings: AIRuntimeSettings | None = None,
) -> None:
    """Enable or disable optional Diffusers memory features consistently."""

    runtime = settings or load_ai_runtime_settings()
    _toggle_feature(
        pipeline,
        runtime.effective_attention_slicing,
        "enable_attention_slicing",
        "disable_attention_slicing",
    )
    _toggle_feature(
        pipeline,
        runtime.effective_vae_slicing,
        "enable_vae_slicing",
        "disable_vae_slicing",
    )
    _toggle_feature(
        pipeline,
        runtime.effective_vae_tiling,
        "enable_vae_tiling",
        "disable_vae_tiling",
    )


class GlobalPretrainedBatikBackgroundProvider(PretrainedBatikBackgroundProvider):
    """Background provider whose memory switches follow the global profile."""

    def _load_pipeline(
        self,
        settings: AIBatikBackgroundOptions,
        mode: str,
    ) -> tuple[Any, Any, str]:
        pipeline, torch, device = super()._load_pipeline(settings, mode)
        configure_pipeline_memory_features(pipeline)
        return pipeline, torch, device


class GlobalPretrainedImg2ImgBatificationProvider(
    PretrainedImg2ImgBatificationProvider
):
    """Object-Batification provider whose memory switches follow the global profile."""

    def _load_pipeline(
        self,
        settings: PretrainedAIBatificationOptions,
    ) -> tuple[Any, Any, str]:
        pipeline, torch, device = super()._load_pipeline(settings)
        configure_pipeline_memory_features(pipeline)
        return pipeline, torch, device


def _toggle_feature(
    pipeline: Any,
    enabled: bool,
    enable_name: str,
    disable_name: str,
) -> None:
    name = enable_name if enabled else disable_name
    callback = getattr(pipeline, name, None)
    if callable(callback):
        callback()


__all__ = [
    "GlobalPretrainedBatikBackgroundProvider",
    "GlobalPretrainedImg2ImgBatificationProvider",
    "apply_global_runtime_to_background_options",
    "configure_pipeline_memory_features",
    "pretrained_batification_options_from_global",
]
