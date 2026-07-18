"""Compatibility fixes for current Diffusers SDXL inference.

The desktop runtime supports several Diffusers releases.  Newer releases move
VAE slicing/tiling controls onto ``pipeline.vae`` and emit noisy warnings when
an UNet-only LoRA is passed through the pipeline-wide loader.  SDXL also has a
hard 77-token CLIP context and used to truncate BatikCraft's most important
creative-direction clauses at the end of the prompt.

This module is installed before the application shell is imported.  It keeps
older Diffusers versions working through fallbacks while using the current APIs
where available.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from batikcraft_studio.ai import batikbrew_generation, global_runtime
from batikcraft_studio.ai.runtime_settings import (
    AIRuntimeSettings,
    load_ai_runtime_settings,
)
from batikcraft_studio.imaging.structured_batification import BatificationError

_INSTALLED = False
_ADAPTER_NAME = "batikbrew"
_PROMPT_FIELDS = (
    "prompt",
    "prompt_2",
    "negative_prompt",
    "negative_prompt_2",
)
_TEXT_ENCODER_PREFIXES = (
    "text_encoder.",
    "text_encoder_2.",
    "lora_te_",
    "lora_te1_",
    "lora_te2_",
    "te1.",
    "te2.",
)
_UNET_PREFIXES = ("unet.", "lora_unet_")


def install_diffusers_inference_compatibility() -> None:
    """Install the SDXL compatibility layer once per process."""

    global _INSTALLED
    if _INSTALLED:
        return

    original_analyse = batikbrew_generation.analyse_inspiration

    def compact_analysis(
        images: list[Any] | tuple[Any, ...],
        *,
        inspiration_name: str,
        custom_direction: str,
        negative_prompt: str,
        trigger_words: tuple[str, ...],
    ) -> Any:
        analysis = original_analyse(
            images,
            inspiration_name=inspiration_name,
            custom_direction=custom_direction,
            negative_prompt=negative_prompt,
            trigger_words=trigger_words,
        )
        positive = _priority_batik_prompt(
            analysis,
            custom_direction=custom_direction,
            trigger_words=trigger_words,
        )
        return replace(analysis, positive_prompt=positive)

    global_runtime.configure_pipeline_memory_features = (
        configure_pipeline_memory_features_compat
    )
    # ``batikbrew_generation`` imports this function directly, so update its
    # module reference as well as the source module.
    batikbrew_generation.configure_pipeline_memory_features = (
        configure_pipeline_memory_features_compat
    )
    batikbrew_generation.analyse_inspiration = compact_analysis
    batikbrew_generation.BatikBrewSDXLGenerationProvider._load_pipeline = (
        _compatible_load_pipeline
    )
    _INSTALLED = True


def configure_pipeline_memory_features_compat(
    pipeline: Any,
    settings: AIRuntimeSettings | None = None,
) -> None:
    """Configure memory features without deprecated pipeline-level VAE calls."""

    runtime = settings or load_ai_runtime_settings()
    _toggle(
        pipeline,
        runtime.effective_attention_slicing,
        "enable_attention_slicing",
        "disable_attention_slicing",
    )

    vae = getattr(pipeline, "vae", None)
    if vae is not None and (
        callable(getattr(vae, "enable_slicing", None))
        or callable(getattr(vae, "disable_slicing", None))
    ):
        _toggle(
            vae,
            runtime.effective_vae_slicing,
            "enable_slicing",
            "disable_slicing",
        )
    else:
        _toggle(
            pipeline,
            runtime.effective_vae_slicing,
            "enable_vae_slicing",
            "disable_vae_slicing",
        )

    if vae is not None and (
        callable(getattr(vae, "enable_tiling", None))
        or callable(getattr(vae, "disable_tiling", None))
    ):
        _toggle(
            vae,
            runtime.effective_vae_tiling,
            "enable_tiling",
            "disable_tiling",
        )
    else:
        _toggle(
            pipeline,
            runtime.effective_vae_tiling,
            "enable_vae_tiling",
            "disable_vae_tiling",
        )


def _compatible_load_pipeline(
    self: Any,
    settings: Any,
) -> tuple[Any, Any, str]:
    """Load SDXL and route UNet-only LoRAs away from text encoders."""

    key = (
        settings.model_id_or_path,
        settings.device,
        settings.precision,
        settings.local_files_only,
        settings.cpu_offload,
        settings.cache_dir,
    )
    with self._load_lock:
        if self._pipeline is not None and self._pipeline_key == key:
            pipeline = self._pipeline
            torch = self._torch
            device = str(self._device)
        else:
            self.unload()
            if self._pipeline_factory is not None:
                pipeline, torch, device = self._pipeline_factory(settings)
            else:
                pipeline, torch, device = (
                    batikbrew_generation._default_sdxl_pipeline_factory(settings)
                )
            self._pipeline = pipeline
            self._pipeline_key = key
            self._torch = torch
            self._device = device

        _install_clip_prompt_guard(pipeline)

        lora_key = (id(pipeline), settings.lora_path, settings.lora_weight)
        if self._lora_key != lora_key:
            unload = getattr(pipeline, "unload_lora_weights", None)
            if callable(unload) and self._lora_key is not None:
                unload()
            weights = Path(settings.lora_path)
            try:
                _load_lora_adapter(
                    pipeline,
                    weights,
                    adapter_name=_ADAPTER_NAME,
                    adapter_weight=float(settings.lora_weight),
                )
            except Exception as exc:
                raise BatificationError(
                    f"LoRA BatikBrew SDXL gagal dimuat: {exc}"
                ) from exc
            self._lora_key = lora_key
        return pipeline, torch, device


def _load_lora_adapter(
    pipeline: Any,
    weights: Path,
    *,
    adapter_name: str,
    adapter_weight: float,
) -> str:
    """Load a LoRA and return ``unet`` or ``pipeline`` for diagnostics/tests."""

    state_loader = getattr(pipeline, "lora_state_dict", None)
    unet_loader = getattr(pipeline, "load_lora_into_unet", None)
    unet = getattr(pipeline, "unet", None)

    if callable(state_loader) and callable(unet_loader) and unet is not None:
        try:
            loaded = state_loader(
                str(weights.parent),
                weight_name=weights.name,
            )
            state_dict, network_alphas = _unpack_lora_state(loaded)
        except Exception:  # noqa: BLE001 - fall back to the official full loader
            state_dict = None
            network_alphas = None

        if state_dict is not None and _is_unet_only_lora(state_dict):
            try:
                unet_loader(
                    state_dict,
                    network_alphas,
                    unet,
                    adapter_name=adapter_name,
                    _pipeline=pipeline,
                )
            except TypeError:
                # Older Diffusers releases do not expose the private pipeline
                # compatibility argument.
                unet_loader(
                    state_dict,
                    network_alphas,
                    unet,
                    adapter_name=adapter_name,
                )
            _set_adapter_weight(pipeline, adapter_name, adapter_weight)
            return "unet"

    full_loader = getattr(pipeline, "load_lora_weights", None)
    if not callable(full_loader):
        raise BatificationError("Pipeline SDXL tidak mendukung pemuatan LoRA.")
    full_loader(
        str(weights.parent),
        weight_name=weights.name,
        adapter_name=adapter_name,
    )
    _set_adapter_weight(pipeline, adapter_name, adapter_weight)
    return "pipeline"


def _unpack_lora_state(
    loaded: object,
) -> tuple[Mapping[str, Any], Mapping[str, Any] | None]:
    if isinstance(loaded, Mapping):
        return loaded, None
    if isinstance(loaded, tuple) and loaded and isinstance(loaded[0], Mapping):
        alphas = loaded[1] if len(loaded) > 1 else None
        return loaded[0], alphas if isinstance(alphas, Mapping) else None
    raise TypeError("State dict LoRA tidak dikenali.")


def _is_unet_only_lora(state_dict: Mapping[str, Any]) -> bool:
    keys = tuple(str(key).casefold() for key in state_dict)
    if not keys:
        return False
    has_text_encoder = any(
        key.startswith(_TEXT_ENCODER_PREFIXES)
        or ".text_encoder." in key
        or ".text_encoder_2." in key
        for key in keys
    )
    has_unet = any(
        key.startswith(_UNET_PREFIXES) or ".unet." in key
        for key in keys
    )
    return has_unet and not has_text_encoder


def _set_adapter_weight(
    pipeline: Any,
    adapter_name: str,
    adapter_weight: float,
) -> None:
    setter = getattr(pipeline, "set_adapters", None)
    if callable(setter):
        setter([adapter_name], adapter_weights=[adapter_weight])
        return
    unet_setter = getattr(getattr(pipeline, "unet", None), "set_adapters", None)
    if callable(unet_setter):
        unet_setter([adapter_name], adapter_weights=[adapter_weight])


def _install_clip_prompt_guard(pipeline: Any) -> None:
    """Ensure all text passed to SDXL's CLIP encoders fits their context."""

    if getattr(pipeline, "_batikcraft_clip_prompt_guard", False):
        return
    original = getattr(pipeline, "encode_prompt", None)
    if not callable(original):
        return
    try:
        signature = inspect.signature(original)
    except (TypeError, ValueError):
        signature = None

    def guarded_encode_prompt(*args: Any, **kwargs: Any) -> Any:
        if signature is not None:
            try:
                bound = signature.bind_partial(*args, **kwargs)
            except TypeError:
                bound = None
            if bound is not None:
                for name in _PROMPT_FIELDS:
                    if name in bound.arguments:
                        bound.arguments[name] = _compact_prompt_value(
                            pipeline,
                            bound.arguments[name],
                        )
                return original(*bound.args, **bound.kwargs)

        safe_kwargs = dict(kwargs)
        for name in _PROMPT_FIELDS:
            if name in safe_kwargs:
                safe_kwargs[name] = _compact_prompt_value(
                    pipeline,
                    safe_kwargs[name],
                )
        return original(*args, **safe_kwargs)

    pipeline.encode_prompt = guarded_encode_prompt
    pipeline._batikcraft_clip_prompt_guard = True


def _compact_prompt_value(pipeline: Any, value: Any) -> Any:
    if isinstance(value, str):
        return _compact_prompt_text(pipeline, value)
    if isinstance(value, tuple):
        return tuple(
            _compact_prompt_text(pipeline, item)
            if isinstance(item, str)
            else item
            for item in value
        )
    if isinstance(value, list):
        return [
            _compact_prompt_text(pipeline, item)
            if isinstance(item, str)
            else item
            for item in value
        ]
    return value


def _compact_prompt_text(pipeline: Any, text: str) -> str:
    tokenizers = _pipeline_tokenizers(pipeline)
    clean = ", ".join(_dedupe_clauses(text))
    if not clean or not tokenizers or _fits_all(tokenizers, clean):
        return clean

    clauses = list(_dedupe_clauses(clean))
    accepted: list[str] = []
    for index, clause in enumerate(clauses):
        candidate = ", ".join((*accepted, clause))
        if _fits_all(tokenizers, candidate):
            accepted.append(clause)
            continue

        important = index < 2 or _important_prompt_clause(clause)
        if important:
            shortened = _longest_clause_prefix(tokenizers, accepted, clause)
            if shortened:
                accepted.append(shortened)

    if accepted:
        return ", ".join(accepted)
    return _truncate_text(tokenizers, clean)


def _pipeline_tokenizers(pipeline: Any) -> tuple[Any, ...]:
    values: list[Any] = []
    for name in ("tokenizer", "tokenizer_2"):
        tokenizer = getattr(pipeline, name, None)
        if tokenizer is None or not callable(getattr(tokenizer, "tokenize", None)):
            continue
        if all(tokenizer is not current for current in values):
            values.append(tokenizer)
    return tuple(values)


def _fits_all(tokenizers: Sequence[Any], text: str) -> bool:
    return all(
        len(tokenizer.tokenize(text)) <= _token_budget(tokenizer)
        for tokenizer in tokenizers
    )


def _token_budget(tokenizer: Any) -> int:
    try:
        maximum = int(getattr(tokenizer, "model_max_length", 77))
    except (TypeError, ValueError):
        maximum = 77
    if maximum <= 2 or maximum > 2048:
        maximum = 77
    return maximum - 2


def _longest_clause_prefix(
    tokenizers: Sequence[Any],
    accepted: Sequence[str],
    clause: str,
) -> str:
    words = clause.split()
    low = 0
    high = len(words)
    best = ""
    while low <= high:
        middle = (low + high) // 2
        prefix = " ".join(words[:middle]).strip(" ,")
        candidate = ", ".join((*accepted, prefix)) if prefix else ", ".join(accepted)
        if prefix and _fits_all(tokenizers, candidate):
            best = prefix
            low = middle + 1
        else:
            high = middle - 1
    return best


def _truncate_text(tokenizers: Sequence[Any], text: str) -> str:
    words = text.split()
    low = 0
    high = len(words)
    best = ""
    while low <= high:
        middle = (low + high) // 2
        candidate = " ".join(words[:middle]).strip(" ,")
        if candidate and _fits_all(tokenizers, candidate):
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return best


def _priority_batik_prompt(
    analysis: Any,
    *,
    custom_direction: str,
    trigger_words: tuple[str, ...],
) -> str:
    direction_parts = list(_dedupe_clauses(custom_direction))
    direction_parts.sort(
        key=lambda clause: 0 if _important_prompt_clause(clause) else 1
    )
    direction = ", ".join(direction_parts)
    palette = " and ".join(analysis.palette_names[:2])
    parts = [
        ", ".join(_dedupe_clauses(", ".join(trigger_words))),
        f"creative direction: {direction}" if direction else "",
        "authentic Indonesian batik ornament",
        ", ".join(analysis.theme_keywords[:2]),
        analysis.style_hints[0] if analysis.style_hints else "",
        f"{palette} palette" if palette else "",
        analysis.composition_hint,
        "canting wax linework",
        "traditional isen-isen",
        "seamless tileable repeat",
    ]
    return ", ".join(
        dict.fromkeys(part.strip(" ,") for part in parts if part.strip(" ,"))
    )


def _dedupe_clauses(text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            clause.strip()
            for clause in str(text).split(",")
            if clause.strip()
        )
    )


def _important_prompt_clause(clause: str) -> bool:
    lowered = clause.casefold()
    return any(
        word in lowered
        for word in (
            "creative direction",
            "preserve",
            "exact",
            "silhouette",
            "subject",
            "object",
            "trigger",
        )
    )


def _toggle(
    component: Any,
    enabled: bool,
    enable_name: str,
    disable_name: str,
) -> None:
    callback = getattr(component, enable_name if enabled else disable_name, None)
    if callable(callback):
        callback()


__all__ = [
    "configure_pipeline_memory_features_compat",
    "install_diffusers_inference_compatibility",
]
