"""Deteksi keluarga model Diffusers (SDXL vs SD 1.5) sebelum generasi.

BatikBrew memakai ``StableDiffusionXLPipeline``. Bila folder yang dipilih
sebenarnya berisi Stable Diffusion 1.5, pemuatan tetap "berhasil" tetapi
generasi meledak jauh di dalam diffusers::

    self.unet.config.addition_time_embed_dim * len(add_time_ids) + ...
    TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'

Modul ini mengubah kegagalan membingungkan itu menjadi pesan yang jelas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FAMILY_SDXL = "sdxl"
FAMILY_SD15 = "sd15"
FAMILY_UNKNOWN = "unknown"

# Komponen yang hanya dimiliki SDXL.
_SDXL_ONLY_COMPONENTS = ("text_encoder_2", "tokenizer_2")


def detect_model_family(model_path: str | Path) -> str:
    """Tebak keluarga model dari struktur folder Diffusers."""

    base = Path(model_path).expanduser()
    if not base.is_dir():
        return FAMILY_UNKNOWN

    index = base / "model_index.json"
    if index.is_file():
        try:
            payload = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        class_name = str(payload.get("_class_name", ""))
        if "XL" in class_name:
            return FAMILY_SDXL
        if class_name.startswith("StableDiffusionPipeline"):
            return FAMILY_SD15

    if all((base / name).is_dir() for name in _SDXL_ONLY_COMPONENTS):
        return FAMILY_SDXL

    unet_config = base / "unet" / "config.json"
    if unet_config.is_file():
        try:
            config = json.loads(unet_config.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            config = {}
        if config.get("addition_time_embed_dim"):
            return FAMILY_SDXL
        if config.get("cross_attention_dim") == 768:
            return FAMILY_SD15
    return FAMILY_UNKNOWN


def describe_family(family: str) -> str:
    return {
        FAMILY_SDXL: "Stable Diffusion XL",
        FAMILY_SD15: "Stable Diffusion 1.5",
    }.get(family, "tidak dikenali")


def sdxl_requirement_message(model_path: str | Path, family: str) -> str:
    """Pesan yang dapat ditindaklanjuti bila model bukan SDXL."""

    return (
        f"Model yang dipilih bukan Stable Diffusion XL (terdeteksi: "
        f"{describe_family(family)}).\n"
        f"Folder: {model_path}\n"
        "BatikBrew memerlukan SDXL Base 1.0 beserta text_encoder_2 dan "
        "tokenizer_2. Buka Pusat Dependensi lalu unduh 'Model BatikBrew SDXL "
        "(base model)', kemudian pilih model itu pada tab Model AI Offline & "
        "LoRA. LoRA .batikmodel untuk SDXL juga tidak dapat dipakai di atas "
        "Stable Diffusion 1.5."
    )


def detect_lora_family(lora_path: str | Path) -> str:
    """Tebak keluarga LoRA dari manifest paket atau isi bobotnya."""

    path = Path(lora_path).expanduser()
    if not path.is_file():
        return FAMILY_UNKNOWN

    # 1) Paket .batikmodel menyimpan base_model_family pada manifest.
    for candidate in (
        path.parent / "manifest.json",
        path.parent.parent / "manifest.json",
    ):
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        model = payload.get("model") if isinstance(payload, dict) else None
        family = str((model or {}).get("base_model_family", "")).casefold()
        if family in {"sdxl", "stable-diffusion-xl", "sd-xl"}:
            return FAMILY_SDXL
        if family in {"sd15", "sd-1.5", "stable-diffusion-1-5", "sd1.5"}:
            return FAMILY_SD15

    # 2) Header safetensors: SDXL memakai dimensi 2048 dan blok text_encoder_2.
    try:
        with path.open("rb") as stream:
            header_size = int.from_bytes(stream.read(8), "little")
            if not 0 < header_size <= 32 * 1024 * 1024:
                return FAMILY_UNKNOWN
            header = json.loads(stream.read(header_size).decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return FAMILY_UNKNOWN

    keys = [key for key in header if key != "__metadata__"]
    if any("text_encoder_2" in key for key in keys):
        return FAMILY_SDXL
    for key in keys:
        entry = header.get(key)
        shape = entry.get("shape") if isinstance(entry, dict) else None
        if not shape:
            continue
        if 2048 in shape:
            return FAMILY_SDXL
        if 768 in shape and "text_model" in key:
            return FAMILY_SD15
    metadata = header.get("__metadata__") or {}
    base = str(metadata.get("ss_base_model_version", "")).casefold()
    if "xl" in base:
        return FAMILY_SDXL
    if base:
        return FAMILY_SD15
    return FAMILY_UNKNOWN


def unet_supports_sdxl(pipeline: Any) -> bool:
    """True bila UNet pipeline benar-benar UNet SDXL."""

    try:
        return bool(getattr(pipeline.unet.config, "addition_time_embed_dim", None))
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "FAMILY_SD15",
    "FAMILY_SDXL",
    "FAMILY_UNKNOWN",
    "describe_family",
    "detect_lora_family",
    "detect_model_family",
    "sdxl_requirement_message",
    "unet_supports_sdxl",
]
