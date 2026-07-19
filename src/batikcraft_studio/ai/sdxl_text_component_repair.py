"""Repair incomplete SDXL prompt components before BatikBrew inference.

Some locally converted Diffusers folders declare ``tokenizer_2`` and
``text_encoder_2`` as optional/empty even though ``StableDiffusionXLPipeline``
will still iterate over both prompt slots whenever the primary tokenizer is
present.  The result is a late ``NoneType has no attribute tokenize`` failure.

This module replaces BatikBrew's default SDXL factory so missing text
components are restored from the selected model folder first and from the
canonical SDXL Base cache/repository second.  Repair happens before device
placement or Accelerate CPU-offload hooks are installed.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from batikcraft_studio.ai import batikbrew_generation
from batikcraft_studio.dependency_bootstrap import (
    activate_managed_ai_packages,
    describe_ai_import_error,
)
from batikcraft_studio.imaging.structured_batification import BatificationError

_INSTALLED = False
_COMPONENT_NAMES = (
    "tokenizer",
    "text_encoder",
    "tokenizer_2",
    "text_encoder_2",
)

ComponentLoader = Callable[[str, str, str, Any, Any], Any]


def install_sdxl_text_component_repair() -> None:
    """Install the complete SDXL factory once per process."""

    global _INSTALLED
    if _INSTALLED:
        return
    batikbrew_generation._default_sdxl_pipeline_factory = (  # type: ignore[attr-defined]
        _complete_sdxl_pipeline_factory
    )
    _INSTALLED = True


def _complete_sdxl_pipeline_factory(settings: Any) -> tuple[Any, Any, str]:
    """Load SDXL, repair prompt components, then configure device placement."""

    activate_managed_ai_packages()
    try:
        import torch
        from diffusers import StableDiffusionXLPipeline
    except ImportError as exc:
        raise BatificationError(describe_ai_import_error(exc)) from exc

    device = batikbrew_generation._resolve_device(torch, settings.device)
    dtype = batikbrew_generation._resolve_dtype(
        torch,
        device,
        settings.precision,
    )
    source = str(settings.model_id_or_path)
    local = Path(source).expanduser()
    model_source = str(local.resolve()) if local.exists() else source

    try:
        pipeline = StableDiffusionXLPipeline.from_pretrained(
            model_source,
            torch_dtype=dtype,
            use_safetensors=True,
            variant="fp16" if dtype == torch.float16 and not local.exists() else None,
            local_files_only=settings.local_files_only,
            cache_dir=settings.cache_dir,
        )
        _repair_sdxl_prompt_components(
            pipeline,
            settings,
            dtype=dtype,
        )

        if settings.cpu_offload and device == "cuda" and hasattr(
            pipeline,
            "enable_model_cpu_offload",
        ):
            pipeline.enable_model_cpu_offload()
        else:
            pipeline.to(device)

        batikbrew_generation.configure_pipeline_memory_features(pipeline)
        progress = getattr(pipeline, "set_progress_bar_config", None)
        if callable(progress):
            progress(disable=True)
    except BatificationError:
        raise
    except Exception as exc:
        raise BatificationError(
            "Model SDXL BatikBrew gagal dimuat. Pastikan folder base model adalah "
            "pipeline SDXL lengkap dan LoRA memang dilatih untuk SDXL. "
            f"Detail: {exc}"
        ) from exc
    return pipeline, torch, device


def _repair_sdxl_prompt_components(
    pipeline: Any,
    settings: Any,
    *,
    dtype: Any = None,
    component_loader: ComponentLoader | None = None,
) -> tuple[str, ...]:
    """Restore missing CLIP tokenizer/encoder pairs required by SDXL.

    Returns the names of components that were restored.  A secondary tokenizer
    may reuse the primary tokenizer only when its vocabulary size matches the
    secondary text encoder; otherwise the real ``tokenizer_2`` is required.
    """

    loader = component_loader or _load_transformers_component
    repaired: list[str] = []

    primary_tokenizer = getattr(pipeline, "tokenizer", None)
    primary_encoder = getattr(pipeline, "text_encoder", None)
    secondary_tokenizer = getattr(pipeline, "tokenizer_2", None)
    secondary_encoder = getattr(pipeline, "text_encoder_2", None)

    # A partially present primary pair makes Diffusers choose the two-encoder
    # branch but zip mismatched tokenizer/encoder lists.  Complete the pair when
    # possible; otherwise discard the partial primary pair and use valid SDXL
    # secondary components only.
    if primary_tokenizer is not None and primary_encoder is None:
        primary_encoder = _try_load_component(
            "text_encoder",
            settings,
            dtype=dtype,
            loader=loader,
        )
        if primary_encoder is not None:
            _register_component(pipeline, "text_encoder", primary_encoder)
            repaired.append("text_encoder")
    elif primary_encoder is not None and primary_tokenizer is None:
        primary_tokenizer = _try_load_component(
            "tokenizer",
            settings,
            dtype=dtype,
            loader=loader,
        )
        if primary_tokenizer is not None:
            _register_component(pipeline, "tokenizer", primary_tokenizer)
            repaired.append("tokenizer")

    primary_tokenizer = getattr(pipeline, "tokenizer", None)
    primary_encoder = getattr(pipeline, "text_encoder", None)
    primary_complete = primary_tokenizer is not None and primary_encoder is not None
    primary_partial = (primary_tokenizer is None) != (primary_encoder is None)

    if secondary_encoder is None:
        secondary_encoder = _try_load_component(
            "text_encoder_2",
            settings,
            dtype=dtype,
            loader=loader,
        )
        if secondary_encoder is not None:
            _register_component(pipeline, "text_encoder_2", secondary_encoder)
            repaired.append("text_encoder_2")

    if secondary_tokenizer is None:
        secondary_tokenizer = _try_load_component(
            "tokenizer_2",
            settings,
            dtype=dtype,
            loader=loader,
        )
        if secondary_tokenizer is None:
            primary_tokenizer = getattr(pipeline, "tokenizer", None)
            secondary_encoder = getattr(pipeline, "text_encoder_2", None)
            if _tokenizer_matches_encoder(primary_tokenizer, secondary_encoder):
                secondary_tokenizer = primary_tokenizer
        if secondary_tokenizer is not None:
            _register_component(pipeline, "tokenizer_2", secondary_tokenizer)
            repaired.append("tokenizer_2")

    secondary_tokenizer = getattr(pipeline, "tokenizer_2", None)
    secondary_encoder = getattr(pipeline, "text_encoder_2", None)
    secondary_complete = (
        secondary_tokenizer is not None and secondary_encoder is not None
    )

    if primary_partial and secondary_complete:
        _register_component(pipeline, "tokenizer", None)
        _register_component(pipeline, "text_encoder", None)
        primary_complete = False
        repaired.extend(("tokenizer", "text_encoder"))

    if not secondary_complete:
        missing = [
            name
            for name in ("tokenizer_2", "text_encoder_2")
            if getattr(pipeline, name, None) is None
        ]
        raise BatificationError(_missing_component_message(settings, missing))

    if getattr(pipeline, "tokenizer", None) is not None and not primary_complete:
        raise BatificationError(
            _missing_component_message(settings, ["tokenizer", "text_encoder"])
        )

    return tuple(dict.fromkeys(repaired))


def _try_load_component(
    name: str,
    settings: Any,
    *,
    dtype: Any,
    loader: ComponentLoader,
) -> Any | None:
    subfolder = name
    for source in _component_sources(settings):
        try:
            return loader(name, source, subfolder, settings, dtype)
        except Exception:  # noqa: BLE001 - try the next authoritative source
            continue
    return None


def _component_sources(settings: Any) -> tuple[str, ...]:
    selected = str(settings.model_id_or_path).strip()
    local = Path(selected).expanduser()
    selected_source = str(local.resolve()) if selected and local.exists() else selected
    canonical = batikbrew_generation.SDXL_BASE_MODEL_ID
    return tuple(
        dict.fromkeys(value for value in (selected_source, canonical) if value)
    )


def _load_transformers_component(
    name: str,
    source: str,
    subfolder: str,
    settings: Any,
    dtype: Any,
) -> Any:
    try:
        from transformers import (
            AutoTokenizer,
            CLIPTextModel,
            CLIPTextModelWithProjection,
        )
    except ImportError as exc:
        raise BatificationError(
            "Transformers diperlukan untuk memulihkan komponen teks SDXL."
        ) from exc

    common = {
        "subfolder": subfolder,
        "local_files_only": bool(settings.local_files_only),
        "cache_dir": settings.cache_dir,
    }
    if name.startswith("tokenizer"):
        return AutoTokenizer.from_pretrained(
            source,
            use_fast=False,
            **common,
        )

    model_class = (
        CLIPTextModelWithProjection if name == "text_encoder_2" else CLIPTextModel
    )
    model_kwargs = dict(common)
    if dtype is not None:
        model_kwargs["torch_dtype"] = dtype
    return model_class.from_pretrained(
        source,
        low_cpu_mem_usage=True,
        **model_kwargs,
    )


def _register_component(pipeline: Any, name: str, value: Any) -> None:
    register = getattr(pipeline, "register_modules", None)
    if callable(register):
        register(**{name: value})
    else:
        setattr(pipeline, name, value)


def _tokenizer_matches_encoder(tokenizer: Any, encoder: Any) -> bool:
    if tokenizer is None or encoder is None:
        return False
    try:
        tokenizer_size = len(tokenizer)
        embeddings = encoder.get_input_embeddings()
        encoder_size = int(embeddings.num_embeddings)
    except (AttributeError, TypeError, ValueError):
        return False
    return int(tokenizer_size) == encoder_size


def _missing_component_message(settings: Any, missing: list[str]) -> str:
    labels = ", ".join(missing) if missing else ", ".join(_COMPONENT_NAMES)
    offline_hint = (
        "Mode local-files-only sedang aktif; unduh/cache SDXL Base lengkap terlebih "
        "dahulu atau nonaktifkan local-files-only sekali untuk pemulihan otomatis."
        if bool(getattr(settings, "local_files_only", False))
        else "Pastikan koneksi tersedia agar komponen SDXL Base dapat dipulihkan."
    )
    return (
        f"Base model SDXL tidak lengkap: komponen {labels} tidak tersedia. "
        "Pilih folder Diffusers SDXL lengkap yang memiliki tokenizer_2 dan "
        f"text_encoder_2. {offline_hint}"
    )


__all__ = [
    "install_sdxl_text_component_repair",
]
