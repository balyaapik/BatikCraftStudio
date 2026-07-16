"""Stable Diffusion img2img Batification with an installed or local LoRA."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageOps, ImageStat

from batikcraft_studio.ai.global_runtime import GlobalPretrainedImg2ImgBatificationProvider
from batikcraft_studio.ai.pretrained_batification import (
    PretrainedAIBatificationOptions,
    PretrainedAIBatificationResult,
    _open_rgba,
    _prepare_square,
    _restore_square,
)
from batikcraft_studio.imaging.non_ml_batification import (
    NonMLBatificationMode,
    NonMLBatificationOptions,
    batify_with_motif,
)
from batikcraft_studio.imaging.structured_batification import BatificationError


@dataclass(frozen=True, slots=True)
class LoraObjectBatificationOptions(PretrainedAIBatificationOptions):
    """Creative controls plus one required Batik LoRA adapter."""

    lora_path: str = ""
    lora_weight: float = 0.85
    lora_trigger_words: tuple[str, ...] = ("bcr_batik",)

    def __post_init__(self) -> None:
        PretrainedAIBatificationOptions.__post_init__(self)
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
            dict.fromkeys(
                str(word).strip()
                for word in self.lora_trigger_words
                if str(word).strip()
            )
        )
        object.__setattr__(self, "lora_path", str(path.resolve()))
        object.__setattr__(self, "lora_weight", weight)
        object.__setattr__(self, "lora_trigger_words", triggers)

    def to_properties(self) -> dict[str, object]:
        properties = PretrainedAIBatificationOptions.to_properties(self)
        properties.update(
            {
                "lora_path": self.lora_path,
                "lora_weight": self.lora_weight,
                "lora_trigger_words": list(self.lora_trigger_words),
            }
        )
        return properties


class LoraObjectBatificationProvider(GlobalPretrainedImg2ImgBatificationProvider):
    """Redraw a source object as a Batik illustration instead of texture-filling it."""

    def __init__(self, pipeline_factory: Any | None = None) -> None:
        super().__init__(pipeline_factory)
        self._lora_key: tuple[int, str, float] | None = None

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

        if hasattr(pipeline, "safety_checker"):
            pipeline.safety_checker = None
        if hasattr(pipeline, "requires_safety_checker"):
            pipeline.requires_safety_checker = False

        key = (id(pipeline), settings.lora_path, settings.lora_weight)
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

        source = _open_rgba(source_content, "objek sumber")
        source_alpha = source.getchannel("A")
        object_mask = _filled_object_mask(source_alpha)
        if object_mask.getbbox() is None:
            raise BatificationError("Objek sumber tidak memiliki area yang dapat dibatifikasi.")

        palette_reference = batify_with_motif(
            source_content,
            motif_content,
            NonMLBatificationOptions(
                mode=NonMLBatificationMode.FILL_OUTLINE,
                pattern_scale=options.pattern_scale,
                preserve_shading=options.preserve_shading,
            ),
        )
        redraw_guide = _build_redraw_guide(
            source,
            object_mask,
            background=palette_reference.palette[-1],
        )
        prepared, restore_box = _prepare_square(
            redraw_guide,
            options.resolution,
            background=palette_reference.palette[-1],
        )

        trigger = ", ".join(options.lora_trigger_words)
        user_prompt = f"{trigger}, {options.prompt}" if trigger else options.prompt
        palette_prompt = ", ".join(palette_reference.palette[:6])
        final_prompt = (
            f"{user_prompt}, redraw the entire subject as an original hand-drawn Indonesian "
            "Batik illustration, reinterpret its anatomy and contours into wax-resist lines, "
            "isen-isen, canting strokes and ornamental negative space, Batik visual language "
            "must shape the object itself, expressive handcrafted contour variation, slightly "
            f"stylized silhouette allowed, motif palette {palette_prompt}"
        )
        negative_prompt = (
            f"{options.negative_prompt}, tiled texture fill, clipped fabric texture, pattern "
            "pasted inside mask, exact traced outline, sticker silhouette, unchanged vector "
            "shape, rectangular textile background, plain object with Batik wallpaper"
        )

        prompt_salt = int.from_bytes(
            hashlib.sha256(final_prompt.encode("utf-8")).digest()[:4],
            "big",
        )
        effective_seed = (int(options.seed) ^ prompt_salt) & 0x7FFFFFFF
        pipeline, torch, device = self._load_pipeline(options)
        generator_device = device if device in {"cpu", "cuda"} else "cpu"
        generator = torch.Generator(device=generator_device).manual_seed(effective_seed)
        effective_strength = max(0.62, min(0.88, options.strength + 0.22))

        with self._inference_lock:
            try:
                response = pipeline(
                    prompt=final_prompt,
                    negative_prompt=negative_prompt,
                    image=prepared.convert("RGB"),
                    strength=effective_strength,
                    num_inference_steps=options.inference_steps,
                    guidance_scale=options.guidance_scale,
                    generator=generator,
                )
            except Exception as exc:
                raise BatificationError(f"Inferensi Stable Diffusion gagal: {exc}") from exc

        images = getattr(response, "images", None)
        if not images:
            raise BatificationError("Model Stable Diffusion tidak menghasilkan gambar.")
        generated = images[0].convert("RGBA")
        restored = _restore_square(generated, restore_box, source.size)

        relaxed_mask = _relaxed_stylization_mask(object_mask)
        restored.putalpha(relaxed_mask)
        guide_weight = max(0.02, min(0.12, (1.0 - options.ai_blend) * 0.18))
        combined = Image.blend(restored, redraw_guide, guide_weight).convert("RGBA")
        combined.putalpha(relaxed_mask)

        output = BytesIO()
        combined.save(output, format="PNG", optimize=True)
        flags = getattr(response, "nsfw_content_detected", None)
        false_positive_ignored = bool(flags and any(bool(value) for value in flags))
        metadata = {
            "pretrained": True,
            "custom_training_required": False,
            "model_id_or_path": options.model_id_or_path,
            "device": device,
            "seed": options.seed,
            "effective_seed": effective_seed,
            "prompt_variation_salt": prompt_salt,
            "inference_steps": options.inference_steps,
            "guidance_scale": options.guidance_scale,
            "requested_strength": options.strength,
            "strength": effective_strength,
            "ai_blend": 1.0 - guide_weight,
            "motif_palette": list(palette_reference.palette),
            "source_mask_coverage": palette_reference.mask_coverage,
            "line_like_source": palette_reference.line_like_source,
            "generation_mode": "batik_redraw_stylization",
            "motif_fill_only": False,
            "source_used_as_redraw_guide": True,
            "original_outline_reapplied": False,
            "silhouette_relaxed": True,
            "prompt": final_prompt,
            "negative_prompt": negative_prompt,
            "local_object_safety_checker_disabled": True,
            "nsfw_false_positive_ignored": false_positive_ignored,
            "lora_path": options.lora_path,
            "lora_weight": options.lora_weight,
            "lora_trigger_words": list(options.lora_trigger_words),
            "stable_diffusion_plus_lora": True,
        }
        return PretrainedAIBatificationResult(
            content=output.getvalue(),
            width=combined.width,
            height=combined.height,
            provider_id=(
                f"pretrained-img2img:{options.model_id_or_path}"
                f"+lora:{Path(options.lora_path).stem}+redraw"
            ),
            metadata=metadata,
        )


def _filled_object_mask(alpha: Image.Image) -> Image.Image:
    """Fill closed transparent-outline objects while preserving solid alpha objects."""

    alpha = alpha.convert("L")
    binary = alpha.point(lambda value: 255 if value >= 20 else 0)
    coverage = _mask_coverage(binary)
    if coverage >= 0.22:
        return alpha

    closed = binary.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(5))
    inverse = ImageOps.invert(closed)
    outside_removed = inverse.copy()
    border_points = (
        (0, 0),
        (outside_removed.width - 1, 0),
        (0, outside_removed.height - 1),
        (outside_removed.width - 1, outside_removed.height - 1),
    )
    for point in border_points:
        ImageDraw.floodfill(outside_removed, point, 0, thresh=8)
    filled = ImageChops.lighter(closed, outside_removed)
    if _mask_coverage(filled) <= coverage * 1.25:
        return alpha.filter(ImageFilter.MaxFilter(5))
    return filled.filter(ImageFilter.GaussianBlur(0.7))


def _build_redraw_guide(
    source: Image.Image,
    mask: Image.Image,
    *,
    background: str,
) -> Image.Image:
    """Build a neutral subject guide, not a repeated Batik texture fill."""

    rgb = source.convert("RGB")
    alpha = source.getchannel("A")
    visible = alpha.point(lambda value: 255 if value >= 20 else 0)
    mean_source = ImageStat.Stat(rgb, mask=visible).mean[:3]
    if not any(mean_source):
        mean_source = ImageColor.getrgb(background)
    mori = ImageColor.getrgb(background)
    interior = tuple(
        round(mori[index] * 0.62 + mean_source[index] * 0.38)
        for index in range(3)
    )

    guide = Image.new("RGBA", source.size, (*mori, 255))
    silhouette = Image.new("RGBA", source.size, (*interior, 255))
    guide.alpha_composite(silhouette)
    guide.putalpha(mask)

    source_detail = source.copy()
    source_detail.putalpha(alpha)
    guide.alpha_composite(source_detail)
    guide.putalpha(mask)
    return guide


def _relaxed_stylization_mask(mask: Image.Image) -> Image.Image:
    """Allow modest contour changes without exposing the square AI background."""

    minimum_side = max(1, min(mask.size))
    radius = max(3, round(minimum_side * 0.018))
    kernel = radius * 2 + 1
    if kernel % 2 == 0:
        kernel += 1
    expanded = mask.convert("L").filter(ImageFilter.MaxFilter(kernel))
    return expanded.filter(ImageFilter.GaussianBlur(max(0.8, radius * 0.32)))


def _mask_coverage(mask: Image.Image) -> float:
    histogram = mask.histogram()
    total = max(1, mask.width * mask.height * 255)
    return sum(index * count for index, count in enumerate(histogram)) / total


__all__ = ["LoraObjectBatificationOptions", "LoraObjectBatificationProvider"]
