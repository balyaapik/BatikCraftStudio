"""Dispatch BatikBrew generation between local SDXL and cloud image APIs."""

from __future__ import annotations

from dataclasses import dataclass, replace

from batikcraft_studio.ai.batikbrew_generation import BatikBrewGenerationOptions
from batikcraft_studio.ai.batikbrew_generation_modes import (
    OUTPUT_MODE_ORNAMENT,
    OUTPUT_MODE_PATTERN,
    BatikBrewModeGenerationOptions,
    BatikBrewModeGenerationProvider,
    _isolate_ornament,
    _with_mode_metadata,
)
from batikcraft_studio.ai.cloud_generation import CloudBatikGenerationProvider
from batikcraft_studio.ai.generation_providers import (
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
    PROVIDER_WATSONX,
)
from batikcraft_studio.ai.pretrained_batification import (
    PretrainedAIBatificationOptions,
    PretrainedAIBatificationResult,
)
from batikcraft_studio.imaging.structured_batification import BatificationError

_CLOUD_PROVIDERS = {PROVIDER_WATSONX, PROVIDER_GEMINI, PROVIDER_OPENAI}
_OUTPUT_MODES = {OUTPUT_MODE_ORNAMENT, OUTPUT_MODE_PATTERN}


@dataclass(frozen=True, slots=True)
class CloudBatikBrewOptions(BatikBrewGenerationOptions):
    """BatikBrew analysis controls for a remote image-generation provider.

    This intentionally bypasses the local LoRA file requirement while retaining the
    same prompt, palette analysis, variation, and output-mode metadata.
    """

    generation_provider: str = PROVIDER_OPENAI
    provider_model: str = ""
    output_mode: str = OUTPUT_MODE_PATTERN

    def __post_init__(self) -> None:
        PretrainedAIBatificationOptions.__post_init__(self)
        provider = str(self.generation_provider).strip().casefold()
        if provider not in _CLOUD_PROVIDERS:
            raise BatificationError("Provider API harus watsonx, Gemini, atau OpenAI.")
        model = str(self.provider_model).strip()
        if not model or len(model) > 500:
            raise BatificationError("Model provider API belum diatur.")
        mode = str(self.output_mode).strip().casefold()
        if mode not in _OUTPUT_MODES:
            raise BatificationError("Mode hasil harus ornament atau pattern.")
        if isinstance(self.variation_count, bool) or not 1 <= int(self.variation_count) <= 4:
            raise BatificationError("Jumlah variasi harus berada antara 1 dan 4.")
        if not isinstance(self.tileable, bool) or not isinstance(
            self.use_secondary_reference, bool
        ):
            raise BatificationError("Pengaturan cloud BatikBrew tidak valid.")
        triggers = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in self.lora_trigger_words
                if str(value).strip()
            )
        )
        object.__setattr__(self, "generation_provider", provider)
        object.__setattr__(self, "provider_model", model)
        object.__setattr__(self, "output_mode", mode)
        object.__setattr__(self, "variation_count", int(self.variation_count))
        object.__setattr__(self, "lora_path", "")
        object.__setattr__(self, "lora_weight", 0.0)
        object.__setattr__(self, "lora_trigger_words", triggers)
        object.__setattr__(self, "inspiration_name", str(self.inspiration_name).strip()[:160])
        if mode == OUTPUT_MODE_ORNAMENT:
            object.__setattr__(self, "tileable", False)

    def to_properties(self) -> dict[str, object]:
        properties = PretrainedAIBatificationOptions.to_properties(self)
        properties.update(
            {
                "generation_provider": self.generation_provider,
                "provider_model": self.provider_model,
                "output_mode": self.output_mode,
                "variation_count": self.variation_count,
                "tileable": self.tileable,
                "inspiration_name": self.inspiration_name,
                "use_secondary_reference": self.use_secondary_reference,
                "lora_trigger_words": list(self.lora_trigger_words),
                "generation_engine": f"batikbrew-cloud-{self.generation_provider}",
                "clipboard_copyable": True,
                "api_key_stored_in_project": False,
            }
        )
        return properties


class HybridBatikGenerationProvider:
    """Keep local SDXL available while adding three selectable cloud providers."""

    def __init__(
        self,
        *,
        local_provider: BatikBrewModeGenerationProvider | None = None,
        cloud_provider: CloudBatikGenerationProvider | None = None,
    ) -> None:
        self.local_provider = local_provider or BatikBrewModeGenerationProvider()
        self.cloud_provider = cloud_provider or CloudBatikGenerationProvider()

    @property
    def is_loaded(self) -> bool:
        return self.local_provider.is_loaded

    def unload(self) -> None:
        self.local_provider.unload()
        self.cloud_provider.unload()

    def render(
        self,
        source_content: bytes,
        motif_content: bytes,
        options: PretrainedAIBatificationOptions | None = None,
    ) -> PretrainedAIBatificationResult:
        return self.render_variations(source_content, motif_content, options)[0]

    def render_variations(
        self,
        source_content: bytes,
        motif_content: bytes,
        options: PretrainedAIBatificationOptions | None = None,
    ) -> tuple[PretrainedAIBatificationResult, ...]:
        if isinstance(options, BatikBrewModeGenerationOptions):
            return self.local_provider.render_variations(source_content, motif_content, options)
        if not isinstance(options, CloudBatikBrewOptions):
            raise BatificationError("Pengaturan provider BatikBrew tidak dikenali.")

        effective = options
        if options.output_mode == OUTPUT_MODE_ORNAMENT:
            effective = replace(
                options,
                prompt=(
                    f"{options.prompt}, exactly one single isolated Indonesian Batik ornament, "
                    "one centered subject only, complete ornamental silhouette, hand-drawn "
                    "canting contour, internal isen-isen, large clean empty margin, plain white "
                    "background, no repeat, no tile, no fabric sheet, no border frame"
                ),
                negative_prompt=(
                    f"{options.negative_prompt}, seamless repeat, tiled pattern, wallpaper, "
                    "multiple motifs, motif grid, background ornament, textured background, "
                    "gradient background, drop shadow, floor shadow, vignette, touching image edge"
                ),
                tileable=False,
            )

        raw = self.cloud_provider.render_variations(source_content, motif_content, effective)
        if options.output_mode == OUTPUT_MODE_ORNAMENT:
            return tuple(_isolate_ornament(item) for item in raw)
        return tuple(_with_mode_metadata(item, OUTPUT_MODE_PATTERN) for item in raw)


__all__ = ["CloudBatikBrewOptions", "HybridBatikGenerationProvider"]
