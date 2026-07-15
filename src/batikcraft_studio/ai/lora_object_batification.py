"""Stable Diffusion img2img Batification with an installed or local LoRA."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from batikcraft_studio.ai.global_runtime import GlobalPretrainedImg2ImgBatificationProvider
from batikcraft_studio.ai.pretrained_batification import (
    PretrainedAIBatificationOptions,
    PretrainedAIBatificationResult,
)
from batikcraft_studio.imaging.structured_batification import BatificationError


@dataclass(frozen=True, slots=True)
class LoraObjectBatificationOptions(PretrainedAIBatificationOptions):
    """Creative controls plus one required Batik LoRA adapter."""

    lora_path: str = ""
    lora_weight: float = 0.85
    lora_trigger_words: tuple[str, ...] = ("bcr_batik",)

    def __post_init__(self) -> None:
        super().__post_init__()
        path = Path(str(self.lora_path).strip()).expanduser()
        if not str(self.lora_path).strip():
            raise BatificationError(
                "Pilih LoRA Batik yang sudah terpasang atau file .safetensors lokal."
            )
        if path.suffix.casefold() not in {".safetensors", ".bin"}:
            raise BatificationError("LoRA harus berupa file .safetensors atau .bin.")
        if not path.is_file():
            raise BatificationError(f"File LoRA tidak ditemukan: {path}")
        weight = float(self.lora_weight)
        if not 0 <= weight <= 2:
            raise BatificationError("Bobot LoRA harus berada antara 0 dan 2.")
        triggers = tuple(
            dict.fromkeys(str(word).strip() for word in self.lora_trigger_words if str(word).strip())
        )
        object.__setattr__(self, "lora_path", str(path.resolve()))
        object.__setattr__(self, "lora_weight", weight)
        object.__setattr__(self, "lora_trigger_words", triggers)

    def to_properties(self) -> dict[str, object]:
        properties = super().to_properties()
        properties.update(
            {
                "lora_path": self.lora_path,
                "lora_weight": self.lora_weight,
                "lora_trigger_words": list(self.lora_trigger_words),
            }
        )
        return properties


class LoraObjectBatificationProvider(GlobalPretrainedImg2ImgBatificationProvider):
    """Load one Batik LoRA on top of the global Stable Diffusion img2img pipeline."""

    def __init__(self, pipeline_factory: Any | None = None) -> None:
        super().__init__(pipeline_factory)
        self._lora_key: tuple[str, float] | None = None

    def unload(self) -> None:
        self._lora_key = None
        super().unload()

    def _load_pipeline(
        self,
        settings: PretrainedAIBatificationOptions,
    ) -> tuple[Any, Any, str]:
        if not isinstance(settings, LoraObjectBatificationOptions):
            raise BatificationError("Batifikasi objek AI memerlukan pengaturan LoRA Batik.")
        pipeline, torch, device = super()._load_pipeline(settings)
        key = (settings.lora_path, settings.lora_weight)
        if self._lora_key == key:
            return pipeline, torch, device

        unload = getattr(pipeline, "unload_lora_weights", None)
        if callable(unload) and self._lora_key is not None:
            unload()
        weights = Path(settings.lora_path)
        loader = getattr(pipeline, "load_lora_weights", None)
        if not callable(loader):
            raise BatificationError("Pipeline Stable Diffusion ini tidak mendukung LoRA.")
        try:
            loader(
                str(weights.parent),
                weight_name=weights.name,
                adapter_name="batikcraft_object",
            )
            set_adapters = getattr(pipeline, "set_adapters", None)
            if callable(set_adapters):
                set_adapters(
                    ["batikcraft_object"],
                    adapter_weights=[settings.lora_weight],
                )
        except Exception as exc:
            raise BatificationError(f"LoRA Batik gagal dimuat: {exc}") from exc
        self._lora_key = key
        return pipeline, torch, device

    def render(
        self,
        source_content: bytes,
        motif_content: bytes,
        options: PretrainedAIBatificationOptions | None = None,
    ) -> PretrainedAIBatificationResult:
        if not isinstance(options, LoraObjectBatificationOptions):
            raise BatificationError("Pilih LoRA Batik sebelum menjalankan Batifikasi AI.")
        trigger = ", ".join(options.lora_trigger_words)
        effective = replace(
            options,
            prompt=f"{trigger}, {options.prompt}" if trigger else options.prompt,
        )
        result = super().render(source_content, motif_content, effective)
        metadata = dict(result.metadata)
        metadata.update(
            {
                "lora_path": options.lora_path,
                "lora_weight": options.lora_weight,
                "lora_trigger_words": list(options.lora_trigger_words),
                "stable_diffusion_plus_lora": True,
            }
        )
        return replace(
            result,
            provider_id=f"{result.provider_id}+lora:{Path(options.lora_path).stem}",
            metadata=metadata,
        )


__all__ = ["LoraObjectBatificationOptions", "LoraObjectBatificationProvider"]
