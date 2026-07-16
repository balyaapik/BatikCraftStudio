from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from PIL import Image, ImageDraw

from batikcraft_studio.ai.lora_object_batification import (
    LoraObjectBatificationOptions,
    LoraObjectBatificationProvider,
    _filled_object_mask,
)


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _outline_leaf() -> bytes:
    image = Image.new("RGBA", (96, 72), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 9, 83, 62), outline=(40, 40, 40, 255), width=4)
    draw.line((18, 57, 78, 14), fill=(40, 40, 40, 255), width=3)
    return _png(image)


def _motif() -> bytes:
    image = Image.new("RGBA", (24, 24), (229, 204, 150, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, 20, 20), outline=(86, 44, 27, 255), width=3)
    draw.line((0, 12, 24, 12), fill=(139, 55, 48, 255), width=2)
    return _png(image)


class _Generator:
    seed: int | None = None

    def manual_seed(self, seed: int) -> _Generator:
        self.seed = seed
        return self


class _Torch:
    generators: list[_Generator] = []

    @classmethod
    def Generator(cls, device: str) -> _Generator:  # noqa: N802
        del device
        generator = _Generator()
        cls.generators.append(generator)
        return generator


class _Pipeline:
    def __init__(self) -> None:
        self.safety_checker = object()
        self.requires_safety_checker = True
        self.prompts: list[str] = []

    def load_lora_weights(self, *_args: object, **_kwargs: object) -> None:
        return None

    def set_adapters(self, *_args: object, **_kwargs: object) -> None:
        return None

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
        prompt = str(kwargs["prompt"])
        self.prompts.append(prompt)
        initial = kwargs["image"]
        assert isinstance(initial, Image.Image)
        generated = initial.convert("RGBA")
        return SimpleNamespace(images=[generated], nsfw_content_detected=[True])


def test_closed_outline_mask_is_filled_inside() -> None:
    with Image.open(BytesIO(_outline_leaf())) as source:
        alpha = source.getchannel("A")
        filled = _filled_object_mask(alpha)
    assert filled.getpixel((48, 36)) > 180
    assert filled.getpixel((2, 2)) < 20


def test_safe_leaf_false_positive_does_not_block_and_interior_is_batik(tmp_path) -> None:
    weights = tmp_path / "batik.safetensors"
    weights.write_bytes(b"lora")
    pipeline = _Pipeline()
    provider = LoraObjectBatificationProvider(lambda _settings: (pipeline, _Torch(), "cpu"))
    options = LoraObjectBatificationOptions(
        model_id_or_path="local/sd15",
        lora_path=str(weights),
        prompt="green parang leaf ornament",
        inference_steps=2,
        resolution=256,
        cpu_offload=False,
    )

    result = provider.render(_outline_leaf(), _motif(), options)

    assert pipeline.safety_checker is None
    assert pipeline.requires_safety_checker is False
    assert result.metadata["nsfw_false_positive_ignored"] is True
    assert result.metadata["interior_batik_fill"] is True
    with Image.open(BytesIO(result.content)) as image:
        image.load()
        assert image.getchannel("A").getpixel((48, 36)) > 180


def test_different_prompts_produce_different_effective_seeds(tmp_path) -> None:
    weights = tmp_path / "batik.safetensors"
    weights.write_bytes(b"lora")
    pipeline = _Pipeline()
    provider = LoraObjectBatificationProvider(lambda _settings: (pipeline, _Torch(), "cpu"))
    common = dict(
        model_id_or_path="local/sd15",
        lora_path=str(weights),
        inference_steps=2,
        resolution=256,
        cpu_offload=False,
        seed=2026,
    )
    first = provider.render(
        _outline_leaf(),
        _motif(),
        LoraObjectBatificationOptions(prompt="parang leaf", **common),
    )
    second = provider.render(
        _outline_leaf(),
        _motif(),
        LoraObjectBatificationOptions(prompt="kawung floral leaf", **common),
    )

    assert first.metadata["effective_seed"] != second.metadata["effective_seed"]
    assert pipeline.prompts[0] != pipeline.prompts[1]
