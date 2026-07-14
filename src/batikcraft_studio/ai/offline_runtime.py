"""Fully offline Diffusers and LoRA Batification provider."""

from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageFilter, ImageOps

from batikcraft_studio.ai.model_pack import InstalledBatikModel
from batikcraft_studio.imaging.structured_batification import (
    BatificationError,
    BatificationRender,
    BatificationRequest,
)


@dataclass(frozen=True, slots=True)
class OfflineRuntimeConfig:
    """Local model locations and conservative inference settings."""

    base_model_path: Path
    controlnet_path: Path | None = None
    device: str = "auto"
    precision: str = "auto"
    inference_steps: int = 28
    guidance_scale: float = 7.0
    controlnet_scale: float = 0.85
    lora_scale: float | None = None
    cpu_offload: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "base_model_path",
            _existing_local_directory(self.base_model_path, "base model"),
        )
        if self.controlnet_path is not None:
            object.__setattr__(
                self,
                "controlnet_path",
                _existing_local_directory(self.controlnet_path, "ControlNet"),
            )
        device = str(self.device).strip().casefold()
        if device not in {"auto", "cpu", "cuda", "mps"}:
            raise BatificationError("device harus auto, cpu, cuda, atau mps.")
        object.__setattr__(self, "device", device)
        precision = str(self.precision).strip().casefold()
        if precision not in {"auto", "float32", "float16", "bfloat16"}:
            raise BatificationError("precision tidak didukung.")
        object.__setattr__(self, "precision", precision)
        if isinstance(self.inference_steps, bool) or not isinstance(self.inference_steps, int):
            raise BatificationError("inference_steps harus berupa bilangan bulat.")
        if not 1 <= self.inference_steps <= 150:
            raise BatificationError("inference_steps harus berada antara 1 dan 150.")
        guidance = float(self.guidance_scale)
        control = float(self.controlnet_scale)
        if not 0 <= guidance <= 30 or not 0 <= control <= 2:
            raise BatificationError("Skala inference tidak valid.")
        object.__setattr__(self, "guidance_scale", guidance)
        object.__setattr__(self, "controlnet_scale", control)
        if self.lora_scale is not None:
            lora = float(self.lora_scale)
            if not 0 <= lora <= 2:
                raise BatificationError("lora_scale harus berada antara 0 dan 2.")
            object.__setattr__(self, "lora_scale", lora)
        if not isinstance(self.cpu_offload, bool):
            raise BatificationError("cpu_offload harus berupa boolean.")


class OfflineLoraBatificationProvider:
    """Run one installed LoRA against local base and ControlNet weights only."""

    def __init__(self, model: InstalledBatikModel, config: OfflineRuntimeConfig) -> None:
        self.model = model
        self.config = config
        self.provider_id = f"offline-lora:{model.model_id}"
        self._pipeline: Any | None = None
        self._torch: Any | None = None
        _enable_offline_environment()

    @property
    def is_loaded(self) -> bool:
        return self._pipeline is not None

    @property
    def lora_scale(self) -> float:
        if self.config.lora_scale is None:
            return self.model.manifest.recommended_weight
        return self.config.lora_scale

    def unload(self) -> None:
        self._pipeline = None
        torch = self._torch
        self._torch = None
        if torch is not None and getattr(torch, "cuda", None) is not None:
            try:
                torch.cuda.empty_cache()
            except RuntimeError:
                pass

    def render(
        self,
        source_content: bytes,
        request: BatificationRequest,
    ) -> BatificationRender:
        source = _open_rgba(source_content)
        alpha = source.getchannel("A")
        if alpha.getbbox() is None:
            raise BatificationError("Source selection sepenuhnya transparan.")
        pipeline, torch, device = self._load_pipeline()
        prepared, restore_box = _prepare_square(
            source,
            self.model.manifest.resolution,
        )
        prompt = _build_prompt(self.model, request)
        generator_device = device if device in {"cpu", "cuda"} else "cpu"
        generator = torch.Generator(device=generator_device).manual_seed(request.seed)
        kwargs: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": self.model.manifest.negative_prompt
            or "photorealistic, text, watermark, blurry, merged objects, solid background",
            "image": prepared.convert("RGB"),
            "strength": max(0.05, min(0.95, request.strength)),
            "num_inference_steps": self.config.inference_steps,
            "guidance_scale": self.config.guidance_scale,
            "generator": generator,
        }
        if self.config.controlnet_path is not None:
            kwargs["control_image"] = _lineart(prepared)
            kwargs["controlnet_conditioning_scale"] = self.config.controlnet_scale
        try:
            generated = pipeline(**kwargs).images[0].convert("RGBA")
        except Exception as exc:
            raise BatificationError(f"Inferensi model offline gagal: {exc}") from exc
        restored = _restore_square(generated, restore_box, source.size)
        restored.putalpha(alpha)
        filler: bytes | None = None
        if request.add_filler:
            details = _detail_component(restored, alpha, request)
            if details.getchannel("A").getbbox() is not None:
                filler = _png(details)
        return BatificationRender(
            content=_png(restored),
            width=source.width,
            height=source.height,
            provider_id=self.provider_id,
            metadata={
                "offline": True,
                "model_id": self.model.model_id,
                "model_version": self.model.manifest.version,
                "base_model_family": self.model.manifest.base_model_family,
                "controlnet_family": self.model.manifest.controlnet_family,
                "trigger_words": list(self.model.manifest.trigger_words),
                "lora_scale": self.lora_scale,
                "inference_steps": self.config.inference_steps,
                "device": device,
                "component_extraction": "high-frequency-alpha-v1",
                "prompt": prompt,
                "seed": request.seed,
            },
            filler_content=filler,
        )

    def _load_pipeline(self) -> tuple[Any, Any, str]:
        if self._pipeline is not None and self._torch is not None:
            return self._pipeline, self._torch, _resolve_device(self._torch, self.config)
        try:
            import torch
            from diffusers import (
                AutoPipelineForImage2Image,
                ControlNetModel,
                StableDiffusionControlNetImg2ImgPipeline,
            )
        except ImportError as exc:
            raise BatificationError(
                "Runtime AI belum terpasang. Instal extra 'batikcraft-studio[ai]'."
            ) from exc
        device = _resolve_device(torch, self.config)
        dtype = _resolve_dtype(torch, device, self.config.precision)
        common = {
            "torch_dtype": dtype,
            "local_files_only": True,
            "safety_checker": None,
            "requires_safety_checker": False,
        }
        try:
            if self.config.controlnet_path is not None:
                controlnet = ControlNetModel.from_pretrained(
                    str(self.config.controlnet_path),
                    torch_dtype=dtype,
                    local_files_only=True,
                )
                pipeline = StableDiffusionControlNetImg2ImgPipeline.from_pretrained(
                    str(self.config.base_model_path),
                    controlnet=controlnet,
                    **common,
                )
            else:
                pipeline = AutoPipelineForImage2Image.from_pretrained(
                    str(self.config.base_model_path),
                    **common,
                )
            pipeline.load_lora_weights(
                str(self.model.lora_path.parent),
                weight_name=self.model.lora_path.name,
                adapter_name="batikcraft_active",
                local_files_only=True,
            )
            if hasattr(pipeline, "set_adapters"):
                pipeline.set_adapters(
                    ["batikcraft_active"],
                    adapter_weights=[self.lora_scale],
                )
            if self.config.cpu_offload and device == "cuda":
                pipeline.enable_model_cpu_offload()
            else:
                pipeline.to(device)
            if hasattr(pipeline, "enable_attention_slicing"):
                pipeline.enable_attention_slicing()
        except Exception as exc:
            raise BatificationError(
                "Model offline gagal dimuat. Pastikan base model, ControlNet, dan LoRA "
                f"kompatibel: {exc}"
            ) from exc
        self._pipeline = pipeline
        self._torch = torch
        return pipeline, torch, device


def _enable_offline_environment() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["DIFFUSERS_OFFLINE"] = "1"
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def _existing_local_directory(value: Path | str, label: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise BatificationError(f"Path {label} harus absolute dan lokal.")
    resolved = path.resolve()
    if not resolved.is_dir():
        raise BatificationError(f"Directory {label} tidak ditemukan: {resolved}")
    return resolved


def _resolve_device(torch: Any, config: OfflineRuntimeConfig) -> str:
    if config.device != "auto":
        if config.device == "cuda" and not torch.cuda.is_available():
            raise BatificationError("CUDA dipilih tetapi GPU CUDA tidak tersedia.")
        if config.device == "mps" and not getattr(torch.backends, "mps", None):
            raise BatificationError("MPS dipilih tetapi backend MPS tidak tersedia.")
        return config.device
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _resolve_dtype(torch: Any, device: str, precision: str) -> Any:
    if precision == "float16":
        return torch.float16
    if precision == "bfloat16":
        return torch.bfloat16
    if precision == "float32":
        return torch.float32
    return torch.float16 if device == "cuda" else torch.float32


def _build_prompt(model: InstalledBatikModel, request: BatificationRequest) -> str:
    parts = [
        *model.manifest.trigger_words,
        request.prompt,
        f"{request.style.value} Indonesian batik motif",
        "clean malam line art",
        "transparent isolated ornament",
        "editable separated component",
    ]
    return ", ".join(part.strip() for part in parts if part and part.strip())


def _prepare_square(
    source: Image.Image,
    resolution: int,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    scale = min(resolution / source.width, resolution / source.height)
    resized = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGB", (resolution, resolution), "white")
    left = (resolution - resized.width) // 2
    top = (resolution - resized.height) // 2
    holder = Image.new("RGBA", resized.size, "white")
    holder.alpha_composite(resized)
    canvas.paste(holder.convert("RGB"), (left, top))
    return canvas.convert("RGBA"), (left, top, left + resized.width, top + resized.height)


def _restore_square(
    generated: Image.Image,
    box: tuple[int, int, int, int],
    size: tuple[int, int],
) -> Image.Image:
    return generated.crop(box).resize(size, Image.Resampling.LANCZOS).convert("RGBA")


def _lineart(image: Image.Image) -> Image.Image:
    gray = ImageOps.autocontrast(image.convert("L"))
    return ImageOps.autocontrast(ImageOps.invert(gray.filter(ImageFilter.FIND_EDGES))).convert("RGB")


def _detail_component(
    generated: Image.Image,
    alpha: Image.Image,
    request: BatificationRequest,
) -> Image.Image:
    gray = ImageOps.autocontrast(generated.convert("L"))
    detail = ImageChops.difference(gray, gray.filter(ImageFilter.GaussianBlur(2.0)))
    threshold = round(35 - 20 * request.isen_density)
    mask = detail.point(lambda value: 255 if value >= threshold else 0)
    mask = ImageChops.multiply(mask.filter(ImageFilter.MaxFilter(3)), alpha)
    output = Image.new("RGBA", generated.size, request.primary_color)
    output.putalpha(mask)
    return output


def _open_rgba(content: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            return source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise BatificationError("Source image tidak dapat dibaca.") from exc


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


__all__ = ["OfflineLoraBatificationProvider", "OfflineRuntimeConfig"]
