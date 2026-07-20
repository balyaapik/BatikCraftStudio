"""Pretrained img2img Batification without custom model training.

The provider uses the deterministic motif-transfer result as the img2img initial
image. A generic pretrained Diffusers model refines that image, after which the
source alpha and a motif-derived outline are restored. This keeps the exact
source silhouette while allowing AI-generated Batik detail before a custom LoRA
has been trained.
"""

from __future__ import annotations

import math
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageColor, ImageFilter

from batikcraft_studio.dependency_bootstrap import (
    activate_managed_ai_packages,
    describe_ai_import_error,
)
from batikcraft_studio.imaging.non_ml_batification import (
    NonMLBatificationMode,
    NonMLBatificationOptions,
    batify_with_motif,
)
from batikcraft_studio.imaging.structured_batification import BatificationError

_DEFAULT_MODEL = "stable-diffusion-v1-5/stable-diffusion-v1-5"
PipelineFactory = Callable[["PretrainedAIBatificationOptions"], tuple[Any, Any, str]]


@dataclass(frozen=True, slots=True)
class PretrainedAIBatificationOptions:
    """Settings for generic pretrained Stable Diffusion img2img Batification."""

    model_id_or_path: str = os.environ.get("BATIKCRAFT_PRETRAINED_MODEL", _DEFAULT_MODEL)
    prompt: str = (
        "authentic Indonesian batik ornament, intricate wax-resist linework, "
        "traditional textile pattern, clean decorative craft, preserve exact object silhouette"
    )
    negative_prompt: str = (
        "photograph, photorealistic, text, watermark, logo, frame, square background, "
        "solid rectangle, changed silhouette, extra object, blurry, low detail"
    )
    strength: float = 0.38
    ai_blend: float = 0.58
    pattern_scale: float = 0.65
    preserve_shading: float = 0.42
    inference_steps: int = 24
    guidance_scale: float = 7.0
    seed: int = 2026
    device: str = "auto"
    precision: str = "auto"
    local_files_only: bool = False
    cpu_offload: bool = True
    cache_dir: str | None = None
    resolution: int = 512

    def __post_init__(self) -> None:
        model = str(self.model_id_or_path).strip()
        if not model:
            raise BatificationError("Model pretrained tidak boleh kosong.")
        prompt = str(self.prompt).strip()
        if not prompt or len(prompt) > 2_000:
            raise BatificationError("Prompt AI harus berisi 1 sampai 2000 karakter.")
        negative = str(self.negative_prompt).strip()
        if len(negative) > 2_000:
            raise BatificationError("Negative prompt maksimal 2000 karakter.")
        strength = _unit(self.strength, "strength")
        ai_blend = _unit(self.ai_blend, "ai_blend")
        pattern_scale = _finite(self.pattern_scale, "pattern_scale")
        shading = _unit(self.preserve_shading, "preserve_shading")
        if not 0.08 <= pattern_scale <= 8.0:
            raise BatificationError("pattern_scale harus berada antara 0.08 dan 8.0.")
        invalid_steps = isinstance(self.inference_steps, bool) or not (
            1 <= int(self.inference_steps) <= 100
        )
        if invalid_steps:
            raise BatificationError("inference_steps harus berada antara 1 dan 100.")
        guidance = _finite(self.guidance_scale, "guidance_scale")
        if not 0 <= guidance <= 30:
            raise BatificationError("guidance_scale harus berada antara 0 dan 30.")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise BatificationError("seed harus berupa bilangan bulat.")
        device = str(self.device).strip().casefold()
        if device not in {"auto", "cpu", "cuda", "mps"}:
            raise BatificationError("device harus auto, cpu, cuda, atau mps.")
        precision = str(self.precision).strip().casefold()
        if precision not in {"auto", "float32", "float16", "bfloat16"}:
            raise BatificationError("precision AI tidak didukung.")
        invalid_flags = not isinstance(self.local_files_only, bool) or not isinstance(
            self.cpu_offload,
            bool,
        )
        if invalid_flags:
            raise BatificationError("Pengaturan download/offload AI harus berupa boolean.")
        invalid_resolution = isinstance(self.resolution, bool) or not (
            256 <= int(self.resolution) <= 1024
        )
        if invalid_resolution:
            raise BatificationError("resolution harus berada antara 256 dan 1024.")
        resolution = max(256, int(round(int(self.resolution) / 8) * 8))
        cache_dir = None if self.cache_dir is None else str(Path(self.cache_dir).expanduser())

        object.__setattr__(self, "model_id_or_path", model)
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "negative_prompt", negative)
        object.__setattr__(self, "strength", strength)
        object.__setattr__(self, "ai_blend", ai_blend)
        object.__setattr__(self, "pattern_scale", pattern_scale)
        object.__setattr__(self, "preserve_shading", shading)
        object.__setattr__(self, "inference_steps", int(self.inference_steps))
        object.__setattr__(self, "guidance_scale", guidance)
        object.__setattr__(self, "device", device)
        object.__setattr__(self, "precision", precision)
        object.__setattr__(self, "cache_dir", cache_dir)
        object.__setattr__(self, "resolution", resolution)

    def to_properties(self) -> dict[str, object]:
        return {
            "model_id_or_path": self.model_id_or_path,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "strength": self.strength,
            "ai_blend": self.ai_blend,
            "pattern_scale": self.pattern_scale,
            "preserve_shading": self.preserve_shading,
            "inference_steps": self.inference_steps,
            "guidance_scale": self.guidance_scale,
            "seed": self.seed,
            "device": self.device,
            "precision": self.precision,
            "local_files_only": self.local_files_only,
            "cpu_offload": self.cpu_offload,
            "cache_dir": self.cache_dir,
            "resolution": self.resolution,
        }


@dataclass(frozen=True, slots=True)
class PretrainedAIBatificationResult:
    """AI Batification PNG and persistence-safe metadata."""

    content: bytes
    width: int
    height: int
    provider_id: str
    metadata: dict[str, object]


class PretrainedImg2ImgBatificationProvider:
    """Refine real motif transfer with a generic pretrained img2img model."""

    def __init__(self, pipeline_factory: PipelineFactory | None = None) -> None:
        self._pipeline_factory = pipeline_factory
        self._pipeline: Any | None = None
        self._torch: Any | None = None
        self._device: str | None = None
        self._pipeline_key: tuple[object, ...] | None = None
        self._load_lock = threading.RLock()
        self._inference_lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._pipeline is not None

    def unload(self) -> None:
        with self._load_lock:
            torch = self._torch
            self._pipeline = None
            self._torch = None
            self._device = None
            self._pipeline_key = None
            if torch is not None and getattr(torch, "cuda", None) is not None:
                try:
                    torch.cuda.empty_cache()
                except RuntimeError:
                    pass

    def render(
        self,
        source_content: bytes,
        motif_content: bytes,
        options: PretrainedAIBatificationOptions | None = None,
    ) -> PretrainedAIBatificationResult:
        settings = options or PretrainedAIBatificationOptions()
        deterministic = batify_with_motif(
            source_content,
            motif_content,
            NonMLBatificationOptions(
                mode=NonMLBatificationMode.FILL_OUTLINE,
                pattern_scale=settings.pattern_scale,
                preserve_shading=settings.preserve_shading,
            ),
        )
        base = _open_rgba(deterministic.content, "hasil motif awal")
        alpha = base.getchannel("A")
        if alpha.getbbox() is None:
            raise BatificationError("Objek sumber tidak memiliki area yang dapat dibatifikasi.")

        prepared, restore_box = _prepare_square(
            base,
            settings.resolution,
            background=deterministic.palette[-1],
        )
        pipeline, torch, device = self._load_pipeline(settings)
        palette_prompt = ", ".join(deterministic.palette[:6])
        prompt = f"{settings.prompt}, motif palette {palette_prompt}"
        generator_device = device if device in {"cpu", "cuda"} else "cpu"
        generator = torch.Generator(device=generator_device).manual_seed(settings.seed)

        with self._inference_lock:
            try:
                response = pipeline(
                    prompt=prompt,
                    negative_prompt=settings.negative_prompt,
                    image=prepared.convert("RGB"),
                    strength=settings.strength,
                    num_inference_steps=settings.inference_steps,
                    guidance_scale=settings.guidance_scale,
                    generator=generator,
                )
            except Exception as exc:
                raise BatificationError(f"Inferensi Stable Diffusion gagal: {exc}") from exc

        flags = getattr(response, "nsfw_content_detected", None)
        if flags and any(bool(value) for value in flags):
            raise BatificationError("Hasil AI diblokir oleh pemeriksaan keamanan model.")
        images = getattr(response, "images", None)
        if not images:
            raise BatificationError("Model pretrained tidak menghasilkan gambar.")
        generated = images[0].convert("RGBA")
        restored = _restore_square(generated, restore_box, base.size)
        restored.putalpha(alpha)

        combined = Image.blend(base, restored, settings.ai_blend).convert("RGBA")
        combined.putalpha(alpha)
        outline = _outline_from_alpha(alpha, deterministic.darkest_color)
        combined.alpha_composite(outline)
        combined.putalpha(alpha)

        output = BytesIO()
        combined.save(output, format="PNG", optimize=True)
        provider_id = f"pretrained-img2img:{settings.model_id_or_path}"
        return PretrainedAIBatificationResult(
            content=output.getvalue(),
            width=combined.width,
            height=combined.height,
            provider_id=provider_id,
            metadata={
                "pretrained": True,
                "custom_training_required": False,
                "model_id_or_path": settings.model_id_or_path,
                "device": device,
                "seed": settings.seed,
                "inference_steps": settings.inference_steps,
                "guidance_scale": settings.guidance_scale,
                "strength": settings.strength,
                "ai_blend": settings.ai_blend,
                "motif_palette": list(deterministic.palette),
                "source_mask_coverage": deterministic.mask_coverage,
                "line_like_source": deterministic.line_like_source,
                "prompt": prompt,
            },
        )

    def _load_pipeline(
        self,
        settings: PretrainedAIBatificationOptions,
    ) -> tuple[Any, Any, str]:
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
                return self._pipeline, self._torch, str(self._device)
            self.unload()
            if self._pipeline_factory is not None:
                pipeline, torch, device = self._pipeline_factory(settings)
            else:
                pipeline, torch, device = _default_pipeline_factory(settings)
            self._pipeline = pipeline
            self._torch = torch
            self._device = device
            self._pipeline_key = key
            return pipeline, torch, device


def _default_pipeline_factory(
    settings: PretrainedAIBatificationOptions,
) -> tuple[Any, Any, str]:
    activate_managed_ai_packages()
    try:
        import torch
        from diffusers import AutoPipelineForImage2Image
    except ImportError as exc:
        raise BatificationError(
            describe_ai_import_error(exc)
        ) from exc

    device = _resolve_device(torch, settings.device)
    dtype = _resolve_dtype(torch, device, settings.precision)
    source = settings.model_id_or_path
    local_path = Path(source).expanduser()
    model_source = str(local_path.resolve()) if local_path.exists() else source
    try:
        pipeline = AutoPipelineForImage2Image.from_pretrained(
            model_source,
            torch_dtype=dtype,
            local_files_only=settings.local_files_only,
            cache_dir=settings.cache_dir,
        )
        if settings.cpu_offload and device == "cuda" and hasattr(
            pipeline,
            "enable_model_cpu_offload",
        ):
            pipeline.enable_model_cpu_offload()
        else:
            pipeline.to(device)
        if hasattr(pipeline, "enable_attention_slicing"):
            pipeline.enable_attention_slicing()
        if hasattr(pipeline, "enable_vae_slicing"):
            pipeline.enable_vae_slicing()
    except Exception as exc:
        download_hint = (
            "Nonaktifkan local_files_only untuk mengunduh model pertama kali."
            if settings.local_files_only
            else "Periksa internet, ruang disk, akses Hugging Face, dan kompatibilitas model."
        )
        message = f"Model pretrained gagal dimuat. {download_hint} Detail: {exc}"
        raise BatificationError(message) from exc
    return pipeline, torch, device


def _prepare_square(
    image: Image.Image,
    resolution: int,
    *,
    background: str,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    scale = min(resolution / image.width, resolution / image.height)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new(
        "RGBA",
        (resolution, resolution),
        (*ImageColor.getrgb(background), 255),
    )
    left = (resolution - resized.width) // 2
    top = (resolution - resized.height) // 2
    canvas.alpha_composite(resized, dest=(left, top))
    return canvas, (left, top, left + resized.width, top + resized.height)


def _restore_square(
    generated: Image.Image,
    box: tuple[int, int, int, int],
    size: tuple[int, int],
) -> Image.Image:
    return generated.crop(box).resize(size, Image.Resampling.LANCZOS).convert("RGBA")


def _outline_from_alpha(alpha: Image.Image, color: str) -> Image.Image:
    outer = alpha.filter(ImageFilter.MaxFilter(5))
    inner = alpha.filter(ImageFilter.MinFilter(3))
    edge = ImageChops.subtract(outer, inner)
    edge = edge.point(lambda value: round(value * 0.78))
    output = Image.new("RGBA", alpha.size, (*ImageColor.getrgb(color), 0))
    output.putalpha(edge)
    return output


def _open_rgba(content: bytes, label: str) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            return source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise BatificationError(f"{label} tidak dapat dibaca.") from exc


def _resolve_device(torch: Any, requested: str) -> str:
    from batikcraft_studio.ai.device_resolution import resolve_torch_device

    return resolve_torch_device(torch, requested)


def _resolve_dtype(torch: Any, device: str, precision: str) -> Any:
    if precision == "float16":
        return torch.float16
    if precision == "bfloat16":
        return torch.bfloat16
    if precision == "float32":
        return torch.float32
    return torch.float16 if device == "cuda" else torch.float32


def _unit(value: object, label: str) -> float:
    number = _finite(value, label)
    if not 0 <= number <= 1:
        raise BatificationError(f"{label} harus berada antara 0 dan 1.")
    return number


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise BatificationError(f"{label} harus berupa angka.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BatificationError(f"{label} harus berupa angka.") from exc
    if not math.isfinite(number):
        raise BatificationError(f"{label} harus berupa angka finite.")
    return number


__all__ = [
    "PretrainedAIBatificationOptions",
    "PretrainedAIBatificationResult",
    "PretrainedImg2ImgBatificationProvider",
]
