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
    "detect_model_family",
    "sdxl_requirement_message",
    "unet_supports_sdxl",
]
