"""Pretrained Stable Diffusion generation for reusable Batik canvas backgrounds."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from batikcraft_studio.dependency_bootstrap import (
    activate_managed_ai_packages,
    describe_ai_import_error,
)
from batikcraft_studio.imaging.structured_batification import BatificationError

_DEFAULT_MODEL = "stable-diffusion-v1-5/stable-diffusion-v1-5"
PipelineFactory = Callable[["AIBatikBackgroundOptions", str], tuple[Any, Any, str]]


@dataclass(frozen=True, slots=True)
class AIBatikBackgroundOptions:
    """Settings for text-to-image or motif-guided Batik background generation."""

    model_id_or_path: str = os.environ.get("BATIKCRAFT_PRETRAINED_MODEL", _DEFAULT_MODEL)
    prompt: str = (
        "seamless authentic Indonesian batik textile pattern, intricate wax-resist "
        "linework, balanced repeating ornament, elegant handcrafted fabric background"
    )
    negative_prompt: str = (
        "photograph, person, face, text, watermark, logo, frame, mockup, perspective, "
        "folded fabric, blurry, low detail, isolated object, empty background"
    )
    inference_steps: int = 28
    guidance_scale: float = 7.5
    seed: int = 2026
    resolution: int = 768
    seamless: bool = True
    reference_strength: float = 0.52
    reference_scale: float = 0.42
    device: str = "auto"
    precision: str = "auto"
    local_files_only: bool = False
    cpu_offload: bool = True
    cache_dir: str | None = None

    def __post_init__(self) -> None:
        model = str(self.model_id_or_path).strip()
        prompt = str(self.prompt).strip()
        negative = str(self.negative_prompt).strip()
        if not model:
            raise BatificationError("Model Stable Diffusion tidak boleh kosong.")
        if not prompt or len(prompt) > 2_000:
            raise BatificationError("Prompt background harus berisi 1 sampai 2000 karakter.")
        if len(negative) > 2_000:
            raise BatificationError("Negative prompt maksimal 2000 karakter.")
        if isinstance(self.inference_steps, bool) or not 1 <= int(self.inference_steps) <= 100:
            raise BatificationError("Inference steps harus berada antara 1 dan 100.")
        guidance = _finite(self.guidance_scale, "guidance_scale")
        if not 0 <= guidance <= 30:
            raise BatificationError("Guidance scale harus berada antara 0 dan 30.")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise BatificationError("Seed harus berupa bilangan bulat.")
        if isinstance(self.resolution, bool) or not 256 <= int(self.resolution) <= 1024:
            raise BatificationError("Resolusi AI harus berada antara 256 dan 1024.")
        strength = _unit(self.reference_strength, "reference_strength")
        scale = _finite(self.reference_scale, "reference_scale")
        if not 0.08 <= scale <= 4.0:
            raise BatificationError("Skala motif referensi harus berada antara 0.08 dan 4.0.")
        device = str(self.device).strip().casefold()
        if device not in {"auto", "cpu", "cuda", "mps"}:
            raise BatificationError("Device harus auto, cpu, cuda, atau mps.")
        precision = str(self.precision).strip().casefold()
        if precision not in {"auto", "float32", "float16", "bfloat16"}:
            raise BatificationError("Precision AI tidak didukung.")
        if not isinstance(self.seamless, bool):
            raise BatificationError("Pengaturan seamless harus berupa boolean.")
        invalid_flags = not isinstance(self.local_files_only, bool) or not isinstance(
            self.cpu_offload,
            bool,
        )
        if invalid_flags:
            raise BatificationError("Pengaturan download/offload AI harus berupa boolean.")
        resolution = max(256, int(round(int(self.resolution) / 8) * 8))
        cache_dir = None if self.cache_dir is None else str(Path(self.cache_dir).expanduser())
        object.__setattr__(self, "model_id_or_path", model)
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "negative_prompt", negative)
        object.__setattr__(self, "inference_steps", int(self.inference_steps))
        object.__setattr__(self, "guidance_scale", guidance)
        object.__setattr__(self, "resolution", resolution)
        object.__setattr__(self, "reference_strength", strength)
        object.__setattr__(self, "reference_scale", scale)
        object.__setattr__(self, "device", device)
        object.__setattr__(self, "precision", precision)
        object.__setattr__(self, "cache_dir", cache_dir)

    def to_properties(self) -> dict[str, object]:
        return {
            "model_id_or_path": self.model_id_or_path,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "inference_steps": self.inference_steps,
            "guidance_scale": self.guidance_scale,
            "seed": self.seed,
            "resolution": self.resolution,
            "seamless": self.seamless,
            "reference_strength": self.reference_strength,
            "reference_scale": self.reference_scale,
            "device": self.device,
            "precision": self.precision,
            "local_files_only": self.local_files_only,
            "cpu_offload": self.cpu_offload,
            "cache_dir": self.cache_dir,
        }


@dataclass(frozen=True, slots=True)
class AIBatikBackgroundResult:
    """Generated background PNG and persistence-safe inference metadata."""

    content: bytes
    width: int
    height: int
    provider_id: str
    metadata: dict[str, object]


class PretrainedBatikBackgroundProvider:
    """Generate a Batik pattern from text, optionally guided by one motif image."""

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
        canvas_width: int,
        canvas_height: int,
        options: AIBatikBackgroundOptions | None = None,
        *,
        reference_content: bytes | None = None,
        reference_name: str | None = None,
    ) -> AIBatikBackgroundResult:
        settings = options or AIBatikBackgroundOptions()
        if canvas_width < 1 or canvas_height < 1:
            raise BatificationError("Ukuran canvas untuk background AI tidak valid.")
        generation_size = _generation_size(canvas_width, canvas_height, settings.resolution)
        mode = "img2img" if reference_content else "text2img"
        pipeline, torch, device = self._load_pipeline(settings, mode)
        generator_device = device if device in {"cpu", "cuda"} else "cpu"
        generator = torch.Generator(device=generator_device).manual_seed(settings.seed)
        prompt = settings.prompt
        if reference_name:
            prompt = f"{prompt}, inspired by reference motif {reference_name}"

        kwargs: dict[str, object] = {
            "prompt": prompt,
            "negative_prompt": settings.negative_prompt,
            "num_inference_steps": settings.inference_steps,
            "guidance_scale": settings.guidance_scale,
            "generator": generator,
        }
        if reference_content is None:
            kwargs.update({"width": generation_size[0], "height": generation_size[1]})
        else:
            reference = _prepare_reference(
                reference_content,
                generation_size,
                scale=settings.reference_scale,
            )
            kwargs.update(
                {
                    "image": reference.convert("RGB"),
                    "strength": settings.reference_strength,
                }
            )

        with self._inference_lock:
            try:
                response = pipeline(**kwargs)
            except Exception as exc:
                message = f"Generasi background Stable Diffusion gagal: {exc}"
                raise BatificationError(message) from exc

        flags = getattr(response, "nsfw_content_detected", None)
        if flags and any(bool(value) for value in flags):
            raise BatificationError(
                "Hasil background AI diblokir oleh pemeriksaan keamanan model."
            )
        images = getattr(response, "images", None)
        if not images:
            raise BatificationError("Model Stable Diffusion tidak menghasilkan background.")
        generated = images[0].convert("RGBA")
        if generated.size != generation_size:
            generated = ImageOps.fit(generated, generation_size, Image.Resampling.LANCZOS)
        if settings.seamless:
            generated = _make_tileable(generated)

        output = BytesIO()
        generated.save(output, format="PNG", optimize=True)
        return AIBatikBackgroundResult(
            content=output.getvalue(),
            width=generated.width,
            height=generated.height,
            provider_id=f"pretrained-background:{settings.model_id_or_path}",
            metadata={
                "pretrained": True,
                "custom_training_required": False,
                "model_id_or_path": settings.model_id_or_path,
                "mode": mode,
                "device": device,
                "seed": settings.seed,
                "inference_steps": settings.inference_steps,
                "guidance_scale": settings.guidance_scale,
                "generation_width": generated.width,
                "generation_height": generated.height,
                "canvas_width": canvas_width,
                "canvas_height": canvas_height,
                "seamless": settings.seamless,
                "reference_name": reference_name,
                "prompt": prompt,
            },
        )

    def _load_pipeline(
        self,
        settings: AIBatikBackgroundOptions,
        mode: str,
    ) -> tuple[Any, Any, str]:
        key = (
            mode,
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
                pipeline, torch, device = self._pipeline_factory(settings, mode)
            else:
                pipeline, torch, device = _default_pipeline_factory(settings, mode)
            self._pipeline = pipeline
            self._torch = torch
            self._device = device
            self._pipeline_key = key
            return pipeline, torch, device


def _default_pipeline_factory(
    settings: AIBatikBackgroundOptions,
    mode: str,
) -> tuple[Any, Any, str]:
    activate_managed_ai_packages()
    try:
        import torch
        from diffusers import AutoPipelineForImage2Image, AutoPipelineForText2Image
    except ImportError as exc:
        raise BatificationError(
            describe_ai_import_error(exc)
        ) from exc

    device = _resolve_device(torch, settings.device)
    dtype = _resolve_dtype(torch, device, settings.precision)
    local_path = Path(settings.model_id_or_path).expanduser()
    source = str(local_path.resolve()) if local_path.exists() else settings.model_id_or_path
    pipeline_class = (
        AutoPipelineForImage2Image if mode == "img2img" else AutoPipelineForText2Image
    )
    try:
        pipeline = pipeline_class.from_pretrained(
            source,
            torch_dtype=dtype,
            local_files_only=settings.local_files_only,
            cache_dir=settings.cache_dir,
        )
        if hasattr(pipeline, "enable_attention_slicing"):
            pipeline.enable_attention_slicing()
        if settings.cpu_offload and device == "cuda" and hasattr(
            pipeline,
            "enable_model_cpu_offload",
        ):
            pipeline.enable_model_cpu_offload()
        else:
            pipeline.to(device)
    except Exception as exc:
        message = (
            f"Model Stable Diffusion {settings.model_id_or_path!r} "
            f"tidak dapat dimuat: {exc}"
        )
        raise BatificationError(message) from exc
    return pipeline, torch, device


def _generation_size(width: int, height: int, resolution: int) -> tuple[int, int]:
    aspect = width / height
    if aspect >= 1.0:
        generated_width = resolution
        generated_height = max(256, int(round((resolution / aspect) / 8) * 8))
    else:
        generated_height = resolution
        generated_width = max(256, int(round((resolution * aspect) / 8) * 8))
    return min(1024, generated_width), min(1024, generated_height)


def _prepare_reference(content: bytes, size: tuple[int, int], *, scale: float) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            motif = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BatificationError("Motif referensi background tidak dapat dibaca.") from exc
    alpha = motif.getchannel("A")
    if alpha.getbbox() is None:
        raise BatificationError("Motif referensi tidak memiliki piksel terlihat.")
    crop = alpha.getbbox()
    if crop is not None:
        motif = motif.crop(crop)
    tile_side = max(32, int(min(size) * scale))
    motif.thumbnail((tile_side, tile_side), Image.Resampling.LANCZOS)
    tile = Image.new("RGBA", (tile_side, tile_side), (244, 233, 216, 255))
    tile.alpha_composite(
        motif,
        ((tile_side - motif.width) // 2, (tile_side - motif.height) // 2),
    )
    canvas = Image.new("RGBA", size, (244, 233, 216, 255))
    for y in range(-tile_side // 2, size[1], tile_side):
        offset = tile_side // 2 if (y // tile_side) % 2 else 0
        for x in range(-tile_side, size[0] + tile_side, tile_side):
            canvas.alpha_composite(tile, (x + offset, y))
    return canvas


def _make_tileable(image: Image.Image) -> Image.Image:
    """Blend paired edge strips so opposite borders contain identical pixels."""

    result = image.convert("RGBA")
    width, height = result.size
    blend = max(2, min(width, height) // 24)
    if width > blend * 2:
        left = result.crop((0, 0, blend, height))
        right = result.crop((width - blend, 0, width, height))
        averaged = Image.blend(left, right, 0.5)
        result.paste(averaged, (0, 0))
        result.paste(averaged, (width - blend, 0))
    if height > blend * 2:
        top = result.crop((0, 0, width, blend))
        bottom = result.crop((0, height - blend, width, height))
        averaged = Image.blend(top, bottom, 0.5)
        result.paste(averaged, (0, 0))
        result.paste(averaged, (0, height - blend))
    return result


def _resolve_device(torch: Any, requested: str) -> str:
    from batikcraft_studio.ai.device_resolution import resolve_torch_device

    return resolve_torch_device(torch, requested)


def _resolve_dtype(torch: Any, device: str, precision: str) -> Any:
    if precision == "float32" or device == "cpu":
        return torch.float32
    if precision == "bfloat16":
        return torch.bfloat16
    if precision == "float16":
        return torch.float16
    return torch.float16 if device in {"cuda", "mps"} else torch.float32


def _finite(value: object, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BatificationError(f"{name} harus berupa angka.") from exc
    if number != number or number in {float("inf"), float("-inf")}:
        raise BatificationError(f"{name} harus berupa angka terbatas.")
    return number


def _unit(value: object, name: str) -> float:
    number = _finite(value, name)
    if not 0.0 <= number <= 1.0:
        raise BatificationError(f"{name} harus berada antara 0 dan 1.")
    return number


__all__ = [
    "AIBatikBackgroundOptions",
    "AIBatikBackgroundResult",
    "PretrainedBatikBackgroundProvider",
]
