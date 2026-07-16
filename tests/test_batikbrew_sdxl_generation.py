from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from PIL import Image, ImageDraw

from batikcraft_studio.ai.batikbrew_generation import (
    BatikBrewGenerationOptions,
    BatikBrewSDXLGenerationProvider,
    analyse_inspiration,
)


def _png(name: str = "leaf") -> tuple[bytes, str]:
    image = Image.new("RGBA", (96, 72), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 8, 84, 63), fill=(54, 110, 62, 255), outline=(30, 55, 31, 255), width=3)
    draw.line((20, 57, 76, 15), fill=(226, 210, 160, 255), width=3)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue(), name


class _Generator:
    def __init__(self) -> None:
        self.seed: int | None = None

    def manual_seed(self, value: int) -> _Generator:
        self.seed = value
        return self


class _Torch:
    class cuda:
        @staticmethod
        def empty_cache() -> None:
            return None

    @staticmethod
    def Generator(device: str) -> _Generator:  # noqa: N802
        del device
        return _Generator()


class _Pipeline:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.loaded_adapter: str | None = None

    def load_lora_weights(self, *_args: object, **kwargs: object) -> None:
        self.loaded_adapter = str(kwargs.get("adapter_name"))

    def set_adapters(self, *_args: object, **_kwargs: object) -> None:
        return None

    def __call__(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(dict(kwargs))
        seed = getattr(kwargs.get("generator"), "seed", 0) or 0
        colour = (60 + seed % 120, 45, 110)
        image = Image.new(
            "RGB",
            (int(kwargs["width"]), int(kwargs["height"])),
            colour,
        )
        return SimpleNamespace(images=[image])


def test_analysis_matches_notebook_palette_theme_and_composition() -> None:
    content, name = _png("green_leaf_fern")
    with Image.open(BytesIO(content)) as source:
        source.load()
        analysis = analyse_inspiration(
            [source.convert("RGBA")],
            inspiration_name=name,
            custom_direction="organic flowing leaf motif",
            negative_prompt="logo",
            trigger_words=("batikbrew",),
        )

    assert analysis.palette_names
    assert "leaf tracery" in analysis.theme_keywords
    assert "traditional Indonesian batik motif" in analysis.positive_prompt
    assert "wax-resist texture" in analysis.positive_prompt
    assert "seamless repeat pattern" in analysis.positive_prompt
    assert "creative direction: organic flowing leaf motif" in analysis.positive_prompt
    assert "logo" in analysis.negative_prompt
    assert 0 <= analysis.edge_density <= 1


def test_sdxl_provider_uses_text_to_image_and_generates_seed_variations(tmp_path) -> None:
    lora = tmp_path / "batikbrew_lora.safetensors"
    lora.write_bytes(b"test-lora")
    pipeline = _Pipeline()
    provider = BatikBrewSDXLGenerationProvider(
        lambda _settings: (pipeline, _Torch(), "cpu")
    )
    source, _name = _png()
    options = BatikBrewGenerationOptions(
        model_id_or_path="local/sdxl",
        lora_path=str(lora),
        lora_trigger_words=("batikbrew",),
        prompt="leaf and parang rhythm",
        inference_steps=2,
        guidance_scale=7.5,
        seed=2026,
        resolution=512,
        variation_count=3,
        tileable=False,
        cpu_offload=False,
        inspiration_name="leaf_fern.png",
    )

    results = provider.render_variations(source, source, options)

    assert len(results) == 3
    assert len(pipeline.calls) == 3
    assert pipeline.loaded_adapter == "batikbrew"
    assert all("image" not in call for call in pipeline.calls)
    assert [result.metadata["variation_index"] for result in results] == [0, 1, 2]
    seeds = [int(result.metadata["seed"]) for result in results]
    assert seeds == [seeds[0], seeds[0] + 1, seeds[0] + 2]
    assert all(
        result.metadata["generation_mode"] == "batikbrew_sdxl_text_to_image"
        for result in results
    )
    assert all(result.metadata["source_used_as_img2img"] is False for result in results)
    assert all(result.metadata["motif_fill_only"] is False for result in results)


def test_render_compatibility_returns_first_variation(tmp_path) -> None:
    lora = tmp_path / "batikbrew_lora.safetensors"
    lora.write_bytes(b"test-lora")
    pipeline = _Pipeline()
    provider = BatikBrewSDXLGenerationProvider(
        lambda _settings: (pipeline, _Torch(), "cpu")
    )
    source, _name = _png()
    options = BatikBrewGenerationOptions(
        model_id_or_path="local/sdxl",
        lora_path=str(lora),
        prompt="mega mendung leaf",
        inference_steps=2,
        resolution=512,
        variation_count=2,
        tileable=False,
        cpu_offload=False,
    )

    result = provider.render(source, source, options)

    assert result.metadata["variation_index"] == 0
    assert len(pipeline.calls) == 2
