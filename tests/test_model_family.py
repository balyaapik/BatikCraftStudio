"""BatikBrew wajib SDXL: SD 1.5 harus ditolak dengan pesan yang jelas."""

from __future__ import annotations

import inspect
import json

from batikcraft_studio.ai import model_family


def _write_model(root, class_name, *, sdxl_components: bool, unet_config: dict):
    root.mkdir(parents=True, exist_ok=True)
    (root / "model_index.json").write_text(
        json.dumps({"_class_name": class_name}), encoding="utf-8"
    )
    (root / "unet").mkdir(exist_ok=True)
    (root / "unet" / "config.json").write_text(
        json.dumps(unet_config), encoding="utf-8"
    )
    names = ["text_encoder", "tokenizer", "vae", "scheduler"]
    if sdxl_components:
        names += ["text_encoder_2", "tokenizer_2"]
    for name in names:
        (root / name).mkdir(exist_ok=True)


def test_detects_sd15_and_sdxl_folders(tmp_path) -> None:
    sd15 = tmp_path / "stable-diffusion-v1-5"
    _write_model(
        sd15,
        "StableDiffusionPipeline",
        sdxl_components=False,
        unet_config={"cross_attention_dim": 768},
    )
    sdxl = tmp_path / "stable-diffusion-xl-base-1.0"
    _write_model(
        sdxl,
        "StableDiffusionXLPipeline",
        sdxl_components=True,
        unet_config={"addition_time_embed_dim": 256, "cross_attention_dim": 2048},
    )

    assert model_family.detect_model_family(sd15) == model_family.FAMILY_SD15
    assert model_family.detect_model_family(sdxl) == model_family.FAMILY_SDXL
    assert model_family.detect_model_family(tmp_path / "tidak-ada") == (
        model_family.FAMILY_UNKNOWN
    )


def test_message_tells_the_user_exactly_what_to_do(tmp_path) -> None:
    message = model_family.sdxl_requirement_message(
        tmp_path / "sd15", model_family.FAMILY_SD15
    )
    assert "bukan Stable Diffusion XL" in message
    assert "Stable Diffusion 1.5" in message
    assert "Pusat Dependensi" in message
    assert "text_encoder_2" in message


def test_unet_without_sdxl_field_is_rejected() -> None:
    class Config:
        addition_time_embed_dim = None

    class Unet:
        config = Config()

    class Pipeline:
        unet = Unet()

    assert model_family.unet_supports_sdxl(Pipeline()) is False

    Config.addition_time_embed_dim = 256
    assert model_family.unet_supports_sdxl(Pipeline()) is True


def test_generation_validates_family_before_and_after_loading() -> None:
    """Regresi lapangan: memuat SD 1.5 sebagai SDXL 'berhasil', lalu gagal di
    dalam diffusers dengan 'NoneType * int' pada addition_time_embed_dim."""

    from batikcraft_studio.ai import batikbrew_generation

    source = inspect.getsource(batikbrew_generation)
    assert "detect_model_family" in source
    assert "unet_supports_sdxl" in source
    assert "sdxl_requirement_message" in source


def test_lora_family_from_batikmodel_manifest(tmp_path) -> None:
    """Paket .batikmodel menyatakan base_model_family; itu sumber paling tepercaya."""

    pack = tmp_path / "batikcraft-style-any-object-v1"
    (pack / "model").mkdir(parents=True)
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "format": "batikcraft-model-pack",
                "model": {"base_model_family": "sd15", "resolution": 512},
            }
        ),
        encoding="utf-8",
    )
    lora = pack / "model" / "pytorch_lora_weights.safetensors"
    # Header safetensors minimal supaya file dapat dibaca.
    header = json.dumps({"__metadata__": {}}).encode("utf-8")
    lora.write_bytes(len(header).to_bytes(8, "little") + header)

    assert model_family.detect_lora_family(lora) == model_family.FAMILY_SD15


def test_lora_family_from_safetensors_header(tmp_path) -> None:
    sdxl_lora = tmp_path / "sdxl.safetensors"
    header = json.dumps(
        {
            "lora_te2_text_model.weight": {"shape": [2048, 64], "dtype": "F16"},
            "__metadata__": {},
        }
    ).encode("utf-8")
    sdxl_lora.write_bytes(len(header).to_bytes(8, "little") + header)
    assert model_family.detect_lora_family(sdxl_lora) == model_family.FAMILY_SDXL

    sd15_lora = tmp_path / "sd15.safetensors"
    header = json.dumps(
        {
            "lora_te_text_model_encoder.weight": {"shape": [768, 32], "dtype": "F16"},
            "__metadata__": {},
        }
    ).encode("utf-8")
    sd15_lora.write_bytes(len(header).to_bytes(8, "little") + header)
    assert model_family.detect_lora_family(sd15_lora) == model_family.FAMILY_SD15


def test_generation_routes_pipeline_by_model_family() -> None:
    """LoRA SD 1.5 harus dijalankan dengan pipeline SD 1.5, bukan dipaksa SDXL
    (penyebab 'NoneType * int' pada addition_time_embed_dim)."""

    from batikcraft_studio.ai import batikbrew_generation

    source = inspect.getsource(batikbrew_generation)
    assert "pipeline_class = StableDiffusionPipeline" in source
    assert "pipeline = pipeline_class.from_pretrained(" in source
    assert "detect_lora_family(settings.lora_path)" in source
    # Ketidakcocokan LoRA vs base model dilaporkan sebelum bobot dimuat.
    assert "LoRA ini dilatih untuk" in source
