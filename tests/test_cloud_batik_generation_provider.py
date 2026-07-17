from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from batikcraft_studio.ai.cloud_generation import CloudBatikGenerationProvider
from batikcraft_studio.ai.generation_providers import (
    PROVIDER_OPENAI,
    CloudGenerationSettings,
    CloudGenerationSettingsStore,
)
from batikcraft_studio.ai.hybrid_batik_generation import (
    CloudBatikBrewOptions,
    HybridBatikGenerationProvider,
)


class _Secrets:
    def get(self, provider_id: str) -> str | None:
        return "test-key" if provider_id == PROVIDER_OPENAI else None


class _UnusedLocalProvider:
    is_loaded = False

    def unload(self) -> None:
        return None

    def render_variations(self, *_args: object, **_kwargs: object) -> tuple[object, ...]:
        raise AssertionError("local provider should not be called")


def _source_png() -> bytes:
    image = Image.new("RGBA", (96, 72), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 8, 84, 63), fill=(54, 110, 62, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _fake_api_image(
    _settings: CloudGenerationSettings,
    _api_key: str,
    _model: str,
    prompt: str,
    output_mode: str,
) -> bytes:
    image = Image.new("RGB", (180, 180), (248, 246, 238))
    draw = ImageDraw.Draw(image)
    if output_mode == "ornament":
        draw.ellipse((46, 34, 134, 146), fill=(91, 43, 31), outline=(35, 22, 17), width=5)
        draw.line((62, 126, 119, 54), fill=(224, 192, 122), width=5)
    else:
        offset = sum(prompt.encode("utf-8")) % 30
        for x in range(-180, 360, 36):
            draw.line((x + offset, 0, x + 180 + offset, 180), fill=(91, 43, 31), width=8)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _provider(tmp_path) -> HybridBatikGenerationProvider:
    settings_store = CloudGenerationSettingsStore(tmp_path / "cloud.json")
    settings_store.save(
        CloudGenerationSettings(
            ornament_provider=PROVIDER_OPENAI,
            pattern_provider=PROVIDER_OPENAI,
        )
    )
    cloud = CloudBatikGenerationProvider(
        settings_store=settings_store,
        secret_store=_Secrets(),  # type: ignore[arg-type]
        generators={PROVIDER_OPENAI: _fake_api_image},
    )
    return HybridBatikGenerationProvider(
        local_provider=_UnusedLocalProvider(),  # type: ignore[arg-type]
        cloud_provider=cloud,
    )


def test_openai_pattern_provider_generates_variations_and_metadata(tmp_path) -> None:
    provider = _provider(tmp_path)
    source = _source_png()
    options = CloudBatikBrewOptions(
        generation_provider=PROVIDER_OPENAI,
        provider_model="gpt-image-1",
        output_mode="pattern",
        prompt="leaf and parang rhythm",
        variation_count=3,
        tileable=False,
        seed=2026,
    )

    results = provider.render_variations(source, source, options)

    assert len(results) == 3
    assert all(result.metadata["generation_provider"] == PROVIDER_OPENAI for result in results)
    assert all(result.metadata["output_mode"] == "pattern" for result in results)
    assert all(result.metadata["api_key_stored_in_project"] is False for result in results)
    assert [result.metadata["variation_index"] for result in results] == [0, 1, 2]


def test_openai_single_ornament_is_cropped_to_transparent_png(tmp_path) -> None:
    provider = _provider(tmp_path)
    source = _source_png()
    options = CloudBatikBrewOptions(
        generation_provider=PROVIDER_OPENAI,
        provider_model="gpt-image-1",
        output_mode="ornament",
        prompt="one leaf as a canting ornament",
        variation_count=1,
        tileable=False,
    )

    result = provider.render(source, source, options)

    assert result.metadata["output_mode"] == "ornament"
    assert result.metadata["transparent_background"] is True
    assert result.width < 180
    assert result.height < 180
    with Image.open(BytesIO(result.content)) as image:
        image.load()
        assert image.mode == "RGBA"
        assert image.getchannel("A").getpixel((0, 0)) == 0
        assert image.getchannel("A").getbbox() is not None
