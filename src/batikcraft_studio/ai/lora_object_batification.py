"""Stable Diffusion img2img Batification with an installed or local LoRA."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageOps

from batikcraft_studio.ai.global_runtime import GlobalPretrainedImg2ImgBatificationProvider
from batikcraft_studio.ai.pretrained_batification import (
    PretrainedAIBatificationOptions,
    PretrainedAIBatificationResult,
    _open_rgba,
    _outline_from_alpha,
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
    """Load one Batik LoRA and generate Batik inside the object's silhouette."""

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

        trigger = ", ".join(options.lora_trigger_words)
        user_prompt = f"{trigger}, {options.prompt}" if trigger else options.prompt
        prompt = (
            f"{user_prompt}, Batik pattern woven and drawn inside the full object body, "
            "interior filled with wax-resist motifs and isen-isen, no separate rectangular "
            "background, preserve the recognizable object anatomy and silhouette"
        )
        negative_prompt = (
            f"{options.negative_prompt}, empty interior, outline only, silhouette sticker, "
            "pattern only behind object, plain object over textile background"
        )

        deterministic = batify_with_motif(
            source_content,
            motif_content,
            NonMLBatificationOptions(
                mode=NonMLBatificationMode.FILL_OUTLINE,
                pattern_scale=options.pattern_scale,
                preserve_shading=options.preserve_shading,
            ),
        )
        source = _open_rgba(source_content, "objek sumber")
        motif = _open_rgba(motif_content, "motif Batik")
        source_alpha = source.getchannel("A")
        object_mask = _filled_object_mask(source_alpha)
        if object_mask.getbbox() is None:
            raise BatificationError("Objek sumber tidak memiliki area yang dapat dibatifikasi.")

        base = _build_interior_batik_base(
            source,
            motif,
            object_mask,
            pattern_scale=options.pattern_scale,
            preserve_shading=options.preserve_shading,
        )
        prepared, restore_box = _prepare_square(
            base,
            options.resolution,
            background=deterministic.palette[-1],
        )
        pipeline, torch, device = self._load_pipeline(options)
        palette_prompt = ", ".join(deterministic.palette[:6])
        final_prompt = f"{prompt}, motif palette {palette_prompt}"

        prompt_salt = int.from_bytes(
            hashlib.sha256(final_prompt.encode("utf-8")).digest()[:4],
            "big",
        )
        effective_seed = (int(options.seed) ^ prompt_salt) & 0x7FFFFFFF
        generator_device = device if device in {"cpu", "cuda"} else "cpu"
        generator = torch.Generator(device=generator_device).manual_seed(effective_seed)

        with self._inference_lock:
            try:
                response = pipeline(
                    prompt=final_prompt,
                    negative_prompt=negative_prompt,
                    image=prepared.convert("RGB"),
                    strength=max(options.strength, 0.48),
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
        restored = _restore_square(generated, restore_box, base.size)
        restored.putalpha(object_mask)

        ai_weight = max(0.68, min(0.92, options.ai_blend + 0.18))
        combined = Image.blend(base, restored, ai_weight).convert("RGBA")
        combined.putalpha(object_mask)

        original_outline = _original_outline(source_alpha, deterministic.darkest_color)
        silhouette_outline = _outline_from_alpha(object_mask, deterministic.darkest_color)
        combined.alpha_composite(silhouette_outline)
        combined.alpha_composite(original_outline)
        combined.putalpha(object_mask)

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
            "strength": max(options.strength, 0.48),
            "ai_blend": ai_weight,
            "motif_palette": list(deterministic.palette),
            "source_mask_coverage": deterministic.mask_coverage,
            "line_like_source": deterministic.line_like_source,
            "filled_object_mask": True,
            "interior_batik_fill": True,
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
                f"+lora:{Path(options.lora_path).stem}"
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


def _build_interior_batik_base(
    source: Image.Image,
    motif: Image.Image,
    mask: Image.Image,
    *,
    pattern_scale: float,
    preserve_shading: float,
) -> Image.Image:
    width, height = source.size
    tile_size = max(
        20,
        round(min(width, height) * max(0.12, min(pattern_scale, 2.5)) / 2.2),
    )
    motif_rgb = motif.convert("RGB")
    ratio = max(tile_size / motif_rgb.width, tile_size / motif_rgb.height)
    resized = motif_rgb.resize(
        (
            max(1, round(motif_rgb.width * ratio)),
            max(1, round(motif_rgb.height * ratio)),
        ),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - tile_size) // 2)
    top = max(0, (resized.height - tile_size) // 2)
    tile = resized.crop((left, top, left + tile_size, top + tile_size))
    texture = Image.new("RGB", (width, height))
    for y in range(0, height, tile.height):
        for x in range(0, width, tile.width):
            texture.paste(tile, (x, y))

    shading = ImageOps.autocontrast(source.convert("L"))
    shading_rgb = Image.merge("RGB", (shading, shading, shading))
    shade_weight = max(0.0, min(0.42, preserve_shading * 0.42))
    textured = Image.blend(texture, ImageChops.multiply(texture, shading_rgb), shade_weight)
    output = textured.convert("RGBA")
    output.putalpha(mask)
    return output


def _original_outline(alpha: Image.Image, color: str) -> Image.Image:
    edge = alpha.filter(ImageFilter.MaxFilter(3))
    output = Image.new("RGBA", alpha.size, (*ImageColor.getrgb(color), 0))
    output.putalpha(edge.point(lambda value: round(value * 0.9)))
    return output


def _mask_coverage(mask: Image.Image) -> float:
    histogram = mask.histogram()
    total = max(1, mask.width * mask.height * 255)
    return sum(index * count for index, count in enumerate(histogram)) / total


__all__ = ["LoraObjectBatificationOptions", "LoraObjectBatificationProvider"]
