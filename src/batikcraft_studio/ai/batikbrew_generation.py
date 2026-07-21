"""BatikBrew SDXL LoRA generation ported from the BatikCraft notebooks.

The notebook workflow is deliberately text-to-image rather than img2img filling:
selected canvas objects are analysed as creative inspiration, converted into Batik
palette/theme/composition clauses, and then rendered by an SDXL Batik LoRA.
"""

from __future__ import annotations

import hashlib
import math
import threading
from dataclasses import dataclass, replace
import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageColor, ImageFilter, ImageOps, ImageStat

from batikcraft_studio.ai.global_runtime import configure_pipeline_memory_features
from batikcraft_studio.ai.pretrained_batification import (
    PretrainedAIBatificationOptions,
    PretrainedAIBatificationResult,
)
from batikcraft_studio.imaging.structured_batification import BatificationError

SDXL_BASE_MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"

_BATIK_PALETTE: tuple[tuple[str, str], ...] = (
    ("sogan brown", "#7A4B2A"),
    ("dark sogan", "#4B2B1B"),
    ("cream", "#E8D8B0"),
    ("ivory", "#F3EAD2"),
    ("indigo", "#243B6B"),
    ("wedel blue", "#365B8C"),
    ("navy", "#15294A"),
    ("forest green", "#355C3A"),
    ("deep olive", "#4D552D"),
    ("terracotta", "#A6573D"),
    ("rust", "#8B3E2F"),
    ("burgundy", "#6B2638"),
    ("charcoal", "#302F2D"),
    ("antique gold", "#B38B43"),
    ("copper gold", "#A86D36"),
    ("mengkudu red", "#8A2F32"),
)

_FILENAME_KEYWORDS = {
    "flower": "floral ornament",
    "floral": "floral ornament",
    "rose": "rose petals",
    "orchid": "orchid blossom",
    "petal": "petal shapes",
    "blossom": "blossom cluster",
    "lily": "lily flower",
    "jasmine": "jasmine motif",
    "bird": "bird silhouette",
    "butterfly": "butterfly wing",
    "peacock": "peacock feather",
    "fish": "fish scale",
    "dragonfly": "dragonfly wing",
    "leaf": "leaf tracery",
    "leaves": "leaf tracery",
    "daun": "leaf tracery",
    "fern": "fern frond",
    "vine": "vine tendril",
    "tree": "tree branch",
    "bamboo": "bamboo stalk",
    "lotus": "lotus petal",
    "temple": "temple relief",
    "candi": "candi ornament",
    "arch": "arch motif",
    "pillar": "column detail",
    "gate": "gate ornament",
    "brick": "brick texture",
    "stone": "stone carving",
    "geometric": "geometric form",
    "ocean": "ocean wave",
    "wave": "wave rhythm",
    "cloud": "cloud arc",
    "awan": "cloud arc",
    "rain": "rain pattern",
    "river": "flowing water",
    "water": "water ripple",
    "fabric": "textile weave",
    "weave": "weave pattern",
    "batik": "batik ornament",
}

_COLOUR_THEME_HINTS = {
    "indigo": "mega mendung cloud motif",
    "wedel blue": "wave and flowing water motif",
    "navy": "deep indigo geometric pattern",
    "sogan brown": "kawung and parang motif",
    "dark sogan": "classical parang rusak motif",
    "forest green": "botanical leaf and vine motif",
    "deep olive": "organic foliage motif",
    "terracotta": "floral and organic ornament",
    "rust": "earthy floral batik motif",
    "cream": "light-ground floral pattern",
    "ivory": "putihan fine-line ornament",
    "antique gold": "ceremonial prada motif",
    "copper gold": "gold-accented ornament",
    "burgundy": "rich ceremonial batik",
    "charcoal": "bold geometric repeat",
}


@dataclass(frozen=True, slots=True)
class BatikBrewGenerationOptions(PretrainedAIBatificationOptions):
    """Creative and runtime controls for notebook-compatible SDXL generation."""

    model_id_or_path: str = SDXL_BASE_MODEL_ID
    prompt: str = "organic Indonesian ornament inspired by the selected object"
    negative_prompt: str = (
        "blurry, low quality, watermark, text, photograph, collage, photorealistic, "
        "3d render, modern graphic design, western pattern, cartoon, distorted"
    )
    inference_steps: int = 30
    guidance_scale: float = 7.5
    resolution: int = 512
    lora_path: str = ""
    lora_weight: float = 1.0
    lora_trigger_words: tuple[str, ...] = ("batikbrew",)
    variation_count: int = 4
    tileable: bool = True
    inspiration_name: str = ""
    use_secondary_reference: bool = False

    def __post_init__(self) -> None:
        PretrainedAIBatificationOptions.__post_init__(self)
        lora = Path(str(self.lora_path).strip()).expanduser()
        if not str(self.lora_path).strip():
            raise BatificationError(
                "Pilih LoRA BatikBrew SDXL yang sudah terpasang atau file safetensors."
            )
        if lora.suffix.casefold() not in {".safetensors", ".bin"}:
            raise BatificationError("LoRA BatikBrew harus berupa .safetensors atau .bin.")
        if not lora.is_file():
            raise BatificationError(f"File LoRA BatikBrew tidak ditemukan: {lora}")
        if not 0 <= float(self.lora_weight) <= 2:
            raise BatificationError("Bobot LoRA harus berada antara 0 dan 2.")
        if isinstance(self.variation_count, bool) or not 1 <= int(self.variation_count) <= 4:
            raise BatificationError("Jumlah variasi harus berada antara 1 dan 4.")
        if not isinstance(self.tileable, bool) or not isinstance(
            self.use_secondary_reference, bool
        ):
            raise BatificationError("Pengaturan BatikBrew tidak valid.")
        triggers = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in self.lora_trigger_words
                if str(value).strip()
            )
        )
        object.__setattr__(self, "lora_path", str(lora.resolve()))
        object.__setattr__(self, "lora_weight", float(self.lora_weight))
        object.__setattr__(self, "lora_trigger_words", triggers)
        object.__setattr__(self, "variation_count", int(self.variation_count))
        object.__setattr__(self, "inspiration_name", str(self.inspiration_name).strip()[:160])

    def to_properties(self) -> dict[str, object]:
        value = PretrainedAIBatificationOptions.to_properties(self)
        value.update(
            {
                "lora_path": self.lora_path,
                "lora_weight": self.lora_weight,
                "lora_trigger_words": list(self.lora_trigger_words),
                "variation_count": self.variation_count,
                "tileable": self.tileable,
                "inspiration_name": self.inspiration_name,
                "use_secondary_reference": self.use_secondary_reference,
                "generation_engine": "batikbrew-sdxl-notebook",
            }
        )
        return value


@dataclass(frozen=True, slots=True)
class BatikBrewAnalysis:
    palette_names: tuple[str, ...]
    palette_hex: tuple[str, ...]
    edge_density: float
    theme_keywords: tuple[str, ...]
    style_hints: tuple[str, ...]
    composition_hint: str
    positive_prompt: str
    negative_prompt: str


class BatikBrewSDXLGenerationProvider:
    """Generate new Batik motifs using the same SDXL LoRA logic as the notebook."""

    def __init__(self, pipeline_factory: Any | None = None) -> None:
        self._pipeline_factory = pipeline_factory
        self._pipeline: Any | None = None
        self._pipeline_key: tuple[object, ...] | None = None
        self._torch: Any | None = None
        self._device: str | None = None
        self._lora_key: tuple[int, str, float] | None = None
        self._load_lock = threading.RLock()
        self._inference_lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._pipeline is not None

    def unload(self) -> None:
        with self._load_lock:
            torch = self._torch
            self._pipeline = None
            self._pipeline_key = None
            self._torch = None
            self._device = None
            self._lora_key = None
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
        """Compatibility entry point returning the first generated variation."""

        return self.render_variations(source_content, motif_content, options)[0]

    def render_variations(
        self,
        source_content: bytes,
        motif_content: bytes,
        options: PretrainedAIBatificationOptions | None = None,
    ) -> tuple[PretrainedAIBatificationResult, ...]:
        if not isinstance(options, BatikBrewGenerationOptions):
            raise BatificationError("Generasi BatikBrew memerlukan pengaturan SDXL LoRA.")

        source = _open_rgb(source_content, "objek inspirasi")
        references = [source]
        if options.use_secondary_reference:
            references.append(_open_rgb(motif_content, "referensi inspirasi kedua"))
        analysis = analyse_inspiration(
            references,
            inspiration_name=options.inspiration_name,
            custom_direction=options.prompt,
            negative_prompt=options.negative_prompt,
            trigger_words=options.lora_trigger_words,
        )
        pipeline, torch, device = self._load_pipeline(options)
        prompt_hash = int.from_bytes(
            hashlib.sha256(analysis.positive_prompt.encode("utf-8")).digest()[:4],
            "big",
        )
        base_seed = (int(options.seed) ^ prompt_hash) & 0x7FFFFFFF
        generator_device = device if device in {"cpu", "cuda"} else "cpu"

        # Pengaman memori: di CPU, RAM tidak cukup berarti proses dibunuh OS
        # (aplikasi "tiba-tiba tertutup"). Periksa dulu, turunkan resolusi bila
        # perlu, dan tolak dengan pesan jelas bila mustahil.
        render_resolution = options.resolution
        # Hanya berlaku untuk pipeline diffusers sungguhan yang benar-benar
        # mengalokasikan tensor besar (pipeline uji/injeksi dilewati).
        real_pipeline = type(pipeline).__module__.split(".")[0] == "diffusers"
        if device == "cpu" and real_pipeline:
            from batikcraft_studio.ai.memory_guard import guard_cpu_generation

            try:
                render_resolution, note = guard_cpu_generation(options.resolution)
            except MemoryError as exc:
                raise BatificationError(str(exc)) from exc
            if note:
                logging.getLogger(__name__).warning(note)

        from batikcraft_studio.ai.generation_trace import trace as _trace_setup

        # Beberapa folder SDXL hasil unduhan/reparasi memiliki
        # unet/config.json dengan "sample_size": null. Diffusers memakai nilai
        # itu pada `height or default_sample_size * vae_scale_factor`, sehingga
        # generasi gagal dengan "unsupported operand type(s) for *: 'NoneType'
        # and 'int'". Pulihkan ke nilai baku SDXL (128 * 8 = 1024 px).
        if getattr(pipeline, "default_sample_size", None) is None:
            try:
                pipeline.default_sample_size = 128
                _trace_setup(
                    "Konfigurasi model tidak menyertakan sample_size; "
                    "memakai nilai baku SDXL (1024 px)."
                )
            except Exception:  # noqa: BLE001
                pass
        if not getattr(pipeline, "vae_scale_factor", None):
            try:
                pipeline.vae_scale_factor = 8
            except Exception:  # noqa: BLE001
                pass

        # Nilai numerik dinormalkan agar tidak ada None yang lolos ke pipeline.
        render_resolution = int(render_resolution or 1024)
        steps = max(1, int(options.inference_steps or 30))
        guidance = float(options.guidance_scale if options.guidance_scale is not None else 7.5)
        variation_total = max(1, int(options.variation_count or 1))
        _trace_setup(
            f"Parameter: {render_resolution}px · {steps} langkah · "
            f"guidance {guidance} · {variation_total} variasi"
        )

        results: list[PretrainedAIBatificationResult] = []

        with self._inference_lock:
            for index in range(variation_total):
                seed = (base_seed + index) & 0x7FFFFFFF
                generator = torch.Generator(device=generator_device).manual_seed(seed)
                from batikcraft_studio.ai.generation_trace import trace as _trace

                _trace(
                    f"Variasi {index + 1}/{variation_total} "
                    f"(seed {seed}, {render_resolution}px, {steps} langkah) dimulai"
                )

                def _step_callback(
                    _pipe: Any, step: int, _timestep: Any, callback_kwargs: dict
                ) -> dict:
                    total_steps = steps
                    if step == 0 or (step + 1) % 5 == 0 or step + 1 >= total_steps:
                        _trace(f"  langkah {step + 1}/{total_steps}")
                    return callback_kwargs

                try:
                    response = pipeline(
                        prompt=analysis.positive_prompt,
                        negative_prompt=analysis.negative_prompt,
                        width=render_resolution,
                        height=render_resolution,
                        num_inference_steps=steps,
                        guidance_scale=guidance,
                        generator=generator,
                        **_step_callback_kwargs(pipeline, _step_callback),
                    )
                except Exception as exc:
                    import traceback

                    detail = traceback.format_exc()
                    logging.getLogger(__name__).error(
                        "Generasi SDXL gagal:\n%s", detail
                    )
                    for line in detail.strip().splitlines()[-8:]:
                        _trace(f"  {line}")
                    raise BatificationError(
                        f"Generasi SDXL BatikBrew gagal: {type(exc).__name__}: {exc}"
                    ) from exc
                images = getattr(response, "images", None)
                if not images:
                    raise BatificationError("SDXL BatikBrew tidak menghasilkan gambar.")
                image = images[0].convert("RGB")
                if options.tileable:
                    image = make_tileable(image)
                encoded = BytesIO()
                image.save(encoded, format="PNG", optimize=True)
                metadata = {
                    "generation_mode": "batikbrew_sdxl_text_to_image",
                    "generation_engine": "batikbrew-sdxl-notebook",
                    "notebook_parity": True,
                    "source_used_as_inspiration": True,
                    "source_used_as_img2img": False,
                    "motif_fill_only": False,
                    "base_model": options.model_id_or_path,
                    "lora_path": options.lora_path,
                    "lora_weight": options.lora_weight,
                    "lora_trigger_words": list(options.lora_trigger_words),
                    "variation_index": index,
                    "variation_count": options.variation_count,
                    "seed": seed,
                    "base_seed": base_seed,
                    "prompt_hash": prompt_hash,
                    "inference_steps": options.inference_steps,
                    "guidance_scale": options.guidance_scale,
                    "tileable": options.tileable,
                    "palette_names": list(analysis.palette_names),
                    "palette_hex": list(analysis.palette_hex),
                    "edge_density": analysis.edge_density,
                    "theme_keywords": list(analysis.theme_keywords),
                    "style_hints": list(analysis.style_hints),
                    "composition_hint": analysis.composition_hint,
                    "prompt": analysis.positive_prompt,
                    "negative_prompt": analysis.negative_prompt,
                    "device": device,
                }
                results.append(
                    PretrainedAIBatificationResult(
                        content=encoded.getvalue(),
                        width=image.width,
                        height=image.height,
                        provider_id=(
                            f"batikbrew-sdxl:{options.model_id_or_path}"
                            f"+lora:{Path(options.lora_path).stem}"
                        ),
                        metadata=metadata,
                    )
                )
        from batikcraft_studio.ai.memory_guard import (
            low_memory_profile,
            release_memory,
        )

        release_memory(torch)
        if low_memory_profile(device, torch):
            # Menahan pipeline di memori berarti menyandera ±7 GB sampai
            # aplikasi ditutup. Pada mesin sempit, lepaskan segera; pemuatan
            # berikutnya jauh lebih cepat karena berkas sudah ada di cache OS.
            logging.getLogger(__name__).info(
                "Profil hemat: melepas pipeline dari memori setelah generasi."
            )
            self.unload()
            release_memory(torch)
        return tuple(results)

    def _load_pipeline(
        self,
        settings: BatikBrewGenerationOptions,
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
                pipeline = self._pipeline
                torch = self._torch
                device = str(self._device)
            else:
                self.unload()
                if self._pipeline_factory is not None:
                    pipeline, torch, device = self._pipeline_factory(settings)
                else:
                    pipeline, torch, device = _default_sdxl_pipeline_factory(settings)
                self._pipeline = pipeline
                self._pipeline_key = key
                self._torch = torch
                self._device = device

            lora_key = (id(pipeline), settings.lora_path, settings.lora_weight)
            if self._lora_key != lora_key:
                unload = getattr(pipeline, "unload_lora_weights", None)
                if callable(unload) and self._lora_key is not None:
                    unload()
                weights = Path(settings.lora_path)
                try:
                    pipeline.load_lora_weights(
                        str(weights.parent),
                        weight_name=weights.name,
                        adapter_name="batikbrew",
                    )
                    setter = getattr(pipeline, "set_adapters", None)
                    if callable(setter):
                        setter(["batikbrew"], adapter_weights=[settings.lora_weight])
                except Exception as exc:
                    raise BatificationError(f"LoRA BatikBrew SDXL gagal dimuat: {exc}") from exc
                self._lora_key = lora_key
            return pipeline, torch, device


def analyse_inspiration(
    images: list[Image.Image] | tuple[Image.Image, ...],
    *,
    inspiration_name: str,
    custom_direction: str,
    negative_prompt: str,
    trigger_words: tuple[str, ...],
) -> BatikBrewAnalysis:
    if not images:
        raise BatificationError("Tidak ada gambar inspirasi untuk dianalisis.")
    palette = _extract_palette(images)
    edge_density = sum(_edge_density(image) for image in images) / len(images)
    themes = _theme_keywords(inspiration_name, palette)
    style_hints = tuple(
        dict.fromkeys(
            _COLOUR_THEME_HINTS[name]
            for name, _hex_value in palette[:4]
            if name in _COLOUR_THEME_HINTS
        )
    )
    if edge_density > 0.25:
        composition = "dense intricate ornament with fine canting lines"
    elif edge_density > 0.10:
        composition = "balanced ornament with flowing curved lines"
    else:
        composition = "soft flowing ornament with smooth ornamental rhythm"

    theme_clause = ", ".join(themes[:4])
    style_clause = style_hints[0] if style_hints else "kawung and parang ornament"
    palette_clause = ", ".join(name for name, _value in palette[:4]) + " palette"
    trigger_clause = ", ".join(trigger_words)
    direction = custom_direction.strip()
    positive = (
        f"{trigger_clause}, " if trigger_clause else ""
    ) + (
        f"traditional Indonesian batik motif inspired by {theme_clause}, "
        f"{style_clause}, {palette_clause}, {composition}, "
        "wax-resist texture, Indonesian textile ornament, seamless repeat pattern, "
        "tileable batik design, authentic canting linework, hand-crafted isen-isen"
    )
    if direction:
        positive = f"{positive}, creative direction: {direction}"
    notebook_negative = (
        "blurry, low quality, watermark, text, photograph, collage, photorealistic, "
        "3d render, modern graphic design, western pattern, cartoon, distorted"
    )
    negative = ", ".join(
        dict.fromkeys(
            item.strip()
            for item in f"{notebook_negative}, {negative_prompt}".split(",")
            if item.strip()
        )
    )
    return BatikBrewAnalysis(
        palette_names=tuple(name for name, _value in palette),
        palette_hex=tuple(value for _name, value in palette),
        edge_density=edge_density,
        theme_keywords=themes,
        style_hints=style_hints,
        composition_hint=composition,
        positive_prompt=positive,
        negative_prompt=negative,
    )


def make_tileable(image: Image.Image, blend: float = 0.12) -> Image.Image:
    """Blend opposite edges using the same strategy as the BatikCraft notebook."""

    try:
        import numpy as np
    except ImportError as exc:
        raise BatificationError(
            'NumPy diperlukan untuk membuat motif tileable. Instal aplikasi dengan extra "[ai]".'
        ) from exc
    arr = np.asarray(image.convert("RGB"), dtype=np.float32)
    height, width = arr.shape[:2]
    blend_width = max(4, int(width * blend))
    blend_height = max(4, int(height * blend))
    result = arr.copy()
    for index in range(blend_width):
        alpha = index / blend_width
        result[:, index, :] = (
            alpha * arr[:, index, :] + (1 - alpha) * arr[:, width - blend_width + index, :]
        )
        result[:, width - 1 - index, :] = (
            alpha * arr[:, width - 1 - index, :]
            + (1 - alpha) * arr[:, blend_width - 1 - index, :]
        )
    for index in range(blend_height):
        alpha = index / blend_height
        result[index, :, :] = (
            alpha * result[index, :, :]
            + (1 - alpha) * arr[height - blend_height + index, :, :]
        )
        result[height - 1 - index, :, :] = (
            alpha * result[height - 1 - index, :, :]
            + (1 - alpha) * arr[blend_height - 1 - index, :, :]
        )
    return Image.fromarray(result.clip(0, 255).astype("uint8"), mode="RGB")


def create_tile_preview(image: Image.Image, grid: tuple[int, int] = (3, 3)) -> Image.Image:
    rows, columns = grid
    tile = image.convert("RGB")
    canvas = Image.new("RGB", (tile.width * columns, tile.height * rows))
    for row in range(rows):
        for column in range(columns):
            canvas.paste(tile, (column * tile.width, row * tile.height))
    return canvas


def _extract_palette(images: list[Image.Image] | tuple[Image.Image, ...]) -> tuple[tuple[str, str], ...]:
    counts: dict[str, int] = {}
    for image in images:
        rgb = _flatten_transparency(image).resize((160, 160), Image.Resampling.LANCZOS)
        quantized = rgb.quantize(colors=6, method=Image.Quantize.MEDIANCUT).convert("RGB")
        for count, color in quantized.getcolors(maxcolors=256) or []:
            name, hex_value = _nearest_batik_colour(color)
            counts[name] = counts.get(name, 0) + int(count)
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    if not ordered:
        ordered = [("sogan brown", 1), ("cream", 1), ("indigo", 1)]
    lookup = dict(_BATIK_PALETTE)
    return tuple((name, lookup[name]) for name, _count in ordered[:6])


def _nearest_batik_colour(rgb: tuple[int, int, int]) -> tuple[str, str]:
    best_name = _BATIK_PALETTE[0][0]
    best_hex = _BATIK_PALETTE[0][1]
    best_distance = math.inf
    for name, hex_value in _BATIK_PALETTE:
        candidate = ImageColor.getrgb(hex_value)
        distance = sum((rgb[index] - candidate[index]) ** 2 for index in range(3))
        if distance < best_distance:
            best_name, best_hex, best_distance = name, hex_value, distance
    return best_name, best_hex


def _edge_density(image: Image.Image) -> float:
    gray = ImageOps.autocontrast(_flatten_transparency(image).convert("L"))
    edge = gray.filter(ImageFilter.FIND_EDGES)
    histogram = edge.histogram()
    active = sum(histogram[32:])
    return active / max(1, edge.width * edge.height)


def _theme_keywords(
    inspiration_name: str,
    palette: tuple[tuple[str, str], ...],
) -> tuple[str, ...]:
    lowered = inspiration_name.casefold().replace("_", " ").replace("-", " ")
    themes: list[str] = []
    for token, keyword in _FILENAME_KEYWORDS.items():
        if token in lowered and keyword not in themes:
            themes.append(keyword)
    for name, _hex_value in palette[:4]:
        hint = _COLOUR_THEME_HINTS.get(name)
        if hint and hint not in themes:
            themes.append(hint)
    if not themes:
        themes.append("organic batik ornament")
    return tuple(themes)


def _flatten_transparency(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (242, 231, 201, 255))
    background.alpha_composite(rgba)
    return background.convert("RGB")


def _open_rgb(content: bytes, label: str) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            return source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise BatificationError(f"{label} tidak dapat dibaca.") from exc


def _default_sdxl_pipeline_factory(
    settings: BatikBrewGenerationOptions,
) -> tuple[Any, Any, str]:
    from batikcraft_studio.dependency_bootstrap import (
        activate_managed_ai_packages,
        describe_ai_import_error,
    )

    try:
        activate_managed_ai_packages()
        import torch
        from diffusers import StableDiffusionXLPipeline
    except ImportError as exc:
        raise BatificationError(describe_ai_import_error(exc)) from exc

    device = _resolve_device(torch, settings.device)
    dtype = _resolve_dtype(torch, device, settings.precision)
    if device == "cpu" and settings.precision in ("auto", "float32"):
        dtype = _cpu_friendly_dtype(torch, dtype)
    source = settings.model_id_or_path
    local = Path(source).expanduser()
    model_source = str(local.resolve()) if local.exists() else source
    # Pemuatan model adalah puncak pemakaian RAM — dan penyebab paling umum
    # aplikasi "tertutup sendiri" (proses dibunuh OS, tanpa dialog).
    from batikcraft_studio.ai.memory_guard import guard_model_load

    logger = logging.getLogger(__name__)
    from batikcraft_studio.ai.generation_trace import (
        describe_compute_environment,
        trace,
    )

    for line in describe_compute_environment(torch):
        trace(line)
    trace(f"Perangkat dipakai: {device} · presisi {dtype}")
    trace(f"Memuat model: {model_source}")
    logger.info(
        "Memuat SDXL: perangkat=%s, dtype=%s, sumber=%s", device, dtype, model_source
    )
    try:
        guard_model_load(device=device, dtype_name=str(dtype), torch_module=torch)
    except MemoryError as exc:
        raise BatificationError(str(exc)) from exc

    try:
        pipeline = StableDiffusionXLPipeline.from_pretrained(
            model_source,
            torch_dtype=dtype,
            use_safetensors=True,
            variant="fp16" if dtype == torch.float16 and not local.exists() else None,
            local_files_only=settings.local_files_only,
            cache_dir=settings.cache_dir,
            # Streaming bobot langsung ke tensor tujuan: puncak RAM turun dari
            # ±2x ukuran model menjadi ±1x. Tanpa ini, mesin dengan RAM sisa
            # sedikit dimatikan OS saat memuat SDXL.
            low_cpu_mem_usage=True,
        )
        logger.info("Bobot SDXL termuat; menyiapkan perangkat…")
        trace("Bobot model termuat, menyiapkan perangkat…")
        from batikcraft_studio.ai.memory_guard import low_memory_profile

        frugal = low_memory_profile(device, torch)
        offload_needed = settings.cpu_offload or _vram_is_tight(torch, device)
        if device == "cuda" and frugal and hasattr(
            pipeline, "enable_sequential_cpu_offload"
        ):
            # Paling hemat: submodul dipindah satu per satu ke GPU sesuai
            # kebutuhan. VRAM puncak turun drastis (cocok untuk 6 GB), dengan
            # konsekuensi lebih lambat.
            logger.info("Profil hemat: sequential CPU offload aktif.")
            trace("Profil hemat: sequential CPU offload aktif (VRAM kecil).")
            pipeline.enable_sequential_cpu_offload()
        elif offload_needed and device == "cuda" and hasattr(
            pipeline, "enable_model_cpu_offload"
        ):
            logger.info("Mengaktifkan model CPU offload (VRAM terbatas).")
            trace("Model CPU offload aktif (VRAM terbatas).")
            pipeline.enable_model_cpu_offload()
        else:
            pipeline.to(device)
        if frugal:
            # Slicing/tiling menekan puncak aktivasi di semua perangkat.
            for memory_feature in (
                "enable_attention_slicing",
                "enable_vae_slicing",
                "enable_vae_tiling",
            ):
                try:
                    getattr(pipeline, memory_feature)()
                except Exception:  # noqa: BLE001
                    continue
            logger.info("Profil hemat memori aktif (slicing + tiling).")
        configure_pipeline_memory_features(pipeline)
        progress = getattr(pipeline, "set_progress_bar_config", None)
        if callable(progress):
            progress(disable=True)
    except Exception as exc:
        raise BatificationError(
            "Model SDXL BatikBrew gagal dimuat. Pastikan runtime SDXL sudah diunduh dan "
            f"LoRA memang dilatih untuk SDXL. Detail: {exc}"
        ) from exc
    logging.getLogger(__name__).info(
        "Pipeline SDXL siap: perangkat=%s, dtype=%s, model=%s",
        device,
        getattr(dtype, "__str__", lambda: "?")(),
        model_source,
    )
    if device == "cpu":
        # Generasi CPU memuat SDXL fp32 (±13 GB) — tanpa slicing puncak RAM
        # bisa membunuh proses (force close). Aktifkan fitur hemat memori.
        logging.getLogger(__name__).warning(
            "Generasi SDXL berjalan di CPU; mengaktifkan attention/vae slicing."
        )
        for memory_feature in (
            "enable_attention_slicing",
            "enable_vae_slicing",
            "enable_vae_tiling",
        ):
            try:
                getattr(pipeline, memory_feature)()
            except Exception:  # noqa: BLE001
                continue
    return pipeline, torch, device


def _resolve_device(torch: Any, requested: str) -> str:
    from batikcraft_studio.ai.device_resolution import resolve_torch_device

    return resolve_torch_device(torch, requested)


def _step_callback_kwargs(pipeline: Any, callback: Any) -> dict[str, Any]:
    """Argumen callback per langkah sesuai versi diffusers yang terpasang."""

    import inspect

    try:
        parameters = inspect.signature(pipeline.__call__).parameters
    except (TypeError, ValueError):
        return {}
    if "callback_on_step_end" in parameters:
        return {"callback_on_step_end": callback}
    if "callback" in parameters:
        # API lama memakai (step, timestep, latents).
        return {
            "callback": lambda step, timestep, latents: callback(
                pipeline, step, timestep, {}
            ),
            "callback_steps": 1,
        }
    return {}


def _vram_is_tight(torch: Any, device: str) -> bool:
    """True bila VRAM GPU < 8 GB — SDXL fp16 butuh ±10 GB tanpa offload.

    RTX kelas laptop (mis. 4050 dengan 6 GB) wajib memakai model CPU offload;
    tanpa itu pemuatan gagal atau proses mati.
    """

    if device != "cuda":
        return False
    try:
        properties = torch.cuda.get_device_properties(0)
        total_gb = float(properties.total_memory) / (1024**3)
    except Exception:  # noqa: BLE001
        return False
    logging.getLogger(__name__).info("VRAM terdeteksi: %.1f GB", total_gb)
    return total_gb < 8.0


def _cpu_friendly_dtype(torch: Any, requested: Any) -> Any:
    """Pilih dtype hemat memori untuk CPU.

    SDXL fp32 menahan ±14 GB bobot saja — di laptop 16 GB proses langsung
    dibunuh OS. bfloat16 memangkas separuhnya dan didukung PyTorch di CPU.
    """

    bfloat16 = getattr(torch, "bfloat16", None)
    if bfloat16 is None or requested is bfloat16:
        return requested
    try:
        torch.zeros(1, dtype=bfloat16) + torch.zeros(1, dtype=bfloat16)
    except Exception:  # noqa: BLE001 - CPU lama tanpa dukungan bf16
        return requested
    logging.getLogger(__name__).info(
        "Generasi CPU memakai bfloat16 (hemat ±50%% memori dibanding float32)."
    )
    return bfloat16


def _resolve_dtype(torch: Any, device: str, precision: str) -> Any:
    if precision == "float16":
        return torch.float16
    if precision == "bfloat16":
        return torch.bfloat16
    if precision == "float32":
        return torch.float32
    return torch.float16 if device == "cuda" else torch.float32


def with_plan_context(
    options: BatikBrewGenerationOptions,
    *,
    source_name: str,
    use_secondary_reference: bool,
) -> BatikBrewGenerationOptions:
    """Attach session-only inspiration context without mutating persisted controls."""

    return replace(
        options,
        inspiration_name=source_name,
        use_secondary_reference=use_secondary_reference,
    )


__all__ = [
    "SDXL_BASE_MODEL_ID",
    "BatikBrewAnalysis",
    "BatikBrewGenerationOptions",
    "BatikBrewSDXLGenerationProvider",
    "analyse_inspiration",
    "create_tile_preview",
    "make_tileable",
    "with_plan_context",
]
