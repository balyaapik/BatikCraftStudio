from __future__ import annotations

import re
from io import BytesIO
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageOps

from batikcraft_studio.ai.lora_object_batification import (
    LoraObjectBatificationOptions,
    LoraObjectBatificationProvider,
)
from batikcraft_studio.ui.batik_palette import BATIK_COLORS
from batikcraft_studio.ui.context_tool_editor_hotfix_v11 import _delete_menu_command


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _source() -> bytes:
    image = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((5, 6, 42, 41), fill=(180, 180, 180, 255))
    return _png(image)


def _motif() -> bytes:
    image = Image.new("RGBA", (16, 16), (224, 187, 108, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 7, 7), fill=(76, 42, 28, 255))
    draw.rectangle((8, 8, 15, 15), fill=(122, 31, 43, 255))
    return _png(image)


class _FakeGenerator:
    def manual_seed(self, _seed: int) -> _FakeGenerator:
        return self


class _FakeTorch:
    @staticmethod
    def Generator(device: str) -> _FakeGenerator:  # noqa: N802 - mimic torch API
        del device
        return _FakeGenerator()


class _FakePipeline:
    def __init__(self) -> None:
        self.loaded: tuple[str, str, str] | None = None
        self.adapters: tuple[list[str], list[float]] | None = None

    def load_lora_weights(self, directory: str, *, weight_name: str, adapter_name: str) -> None:
        self.loaded = (directory, weight_name, adapter_name)

    def set_adapters(self, names: list[str], *, adapter_weights: list[float]) -> None:
        self.adapters = (names, adapter_weights)

    def enable_attention_slicing(self) -> None:
        return None

    def disable_attention_slicing(self) -> None:
        return None

    def enable_vae_slicing(self) -> None:
        return None

    def disable_vae_slicing(self) -> None:
        return None

    def enable_vae_tiling(self) -> None:
        return None

    def disable_vae_tiling(self) -> None:
        return None

    def __call__(self, **kwargs: object) -> SimpleNamespace:
        initial = kwargs["image"]
        assert isinstance(initial, Image.Image)
        generated = ImageOps.colorize(
            ImageOps.autocontrast(initial.convert("L")),
            black=(45, 24, 17),
            white=(214, 159, 74),
        ).convert("RGBA")
        return SimpleNamespace(images=[generated], nsfw_content_detected=[False])


class _FakeMenu:
    def __init__(self, entries: list[tuple[str, str]]) -> None:
        self.entries = entries

    def index(self, value: str) -> int | None:
        assert value == "end"
        return len(self.entries) - 1 if self.entries else None

    def entrycget(self, index: int, option: str) -> str:
        assert option == "label"
        return self.entries[index][1]

    def type(self, index: int) -> str:
        return self.entries[index][0]

    def delete(self, index: int) -> None:
        del self.entries[index]


def test_expanded_palette_contains_named_traditional_batik_families() -> None:
    assert len(BATIK_COLORS) >= 60
    names = {color.name for color in BATIK_COLORS}
    families = {color.family for color in BATIK_COLORS}
    assert {"Hitam Malam", "Soga Klasik", "Merah Mengkudu", "Indigo"} <= names
    assert {"Soga & Tanah", "Nila & Pesisir", "Hijau Alam"} <= families
    assert len(names) == len(BATIK_COLORS)
    assert all(re.fullmatch(r"#[0-9A-F]{6}", color.hex_value) for color in BATIK_COLORS)


def test_lora_object_provider_loads_adapter_and_records_metadata(tmp_path) -> None:
    weights = tmp_path / "batik-style.safetensors"
    weights.write_bytes(b"test-lora")
    pipeline = _FakePipeline()
    provider = LoraObjectBatificationProvider(
        lambda _options: (pipeline, _FakeTorch(), "cpu")
    )
    options = LoraObjectBatificationOptions(
        model_id_or_path="fake/model",
        lora_path=str(weights),
        lora_weight=0.92,
        lora_trigger_words=("bcr_batik", "batik style"),
        inference_steps=2,
        resolution=256,
        cpu_offload=False,
    )

    result = provider.render(_source(), _motif(), options)

    assert pipeline.loaded == (str(tmp_path), weights.name, "batikcraft_object")
    assert pipeline.adapters == (["batikcraft_object"], [0.92])
    assert result.metadata["stable_diffusion_plus_lora"] is True
    assert result.metadata["lora_weight"] == 0.92
    assert "lora:batik-style" in result.provider_id
    assert options.to_properties()["lora_trigger_words"] == ["bcr_batik", "batik style"]


def test_ai_background_context_command_can_be_removed_with_separator() -> None:
    menu = _FakeMenu(
        [
            ("command", "Batifikasi Objek dengan AI & LoRA…"),
            ("separator", ""),
            ("command", "AI Batik Background…"),
        ]
    )

    assert _delete_menu_command(menu, "AI Batik Background…") is True
    assert menu.entries == [("command", "Batifikasi Objek dengan AI & LoRA…")]
