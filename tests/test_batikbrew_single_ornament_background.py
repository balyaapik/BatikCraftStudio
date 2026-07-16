from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

from batikcraft_studio.ai.batikbrew_generation_modes import (
    _background_alpha,
    _isolate_ornament,
)
from batikcraft_studio.ai.pretrained_batification import PretrainedAIBatificationResult


def _generated_style_ornament() -> Image.Image:
    width, height = 220, 180
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            shade = round(246 - 12 * (x / width) - 7 * (y / height))
            pixels[x, y] = (shade, shade - 3, shade - 9)

    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.ellipse((55, 118, 171, 151), fill=(75, 55, 35, 52))
    shadow = shadow.filter(ImageFilter.GaussianBlur(9))
    composed = image.convert("RGBA")
    composed.alpha_composite(shadow)

    draw = ImageDraw.Draw(composed)
    draw.ellipse(
        (66, 33, 159, 132),
        fill=(92, 47, 32, 255),
        outline=(42, 24, 20, 255),
        width=5,
    )
    draw.line((80, 112, 144, 51), fill=(226, 198, 134, 255), width=5)
    draw.arc((83, 50, 151, 117), 15, 170, fill=(225, 184, 116, 255), width=3)
    return composed


def test_background_alpha_removes_gradient_and_shadow() -> None:
    image = _generated_style_ornament()
    alpha = _background_alpha(image)

    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getpixel((image.width - 1, image.height - 1)) == 0
    assert alpha.getpixel((110, 82)) > 180
    assert alpha.getpixel((110, 155)) < 40

    histogram = alpha.histogram()
    coverage = sum(histogram[1:]) / (alpha.width * alpha.height)
    assert 0.05 < coverage < 0.55


def test_isolate_ornament_returns_cropped_transparent_png() -> None:
    image = _generated_style_ornament()
    encoded = BytesIO()
    image.save(encoded, format="PNG")
    result = PretrainedAIBatificationResult(
        content=encoded.getvalue(),
        width=image.width,
        height=image.height,
        provider_id="test",
        metadata={},
    )

    isolated = _isolate_ornament(result)

    assert isolated.width < image.width
    assert isolated.height < image.height
    assert isolated.metadata["background_removed"] is True
    assert isolated.metadata["transparent_background"] is True
    assert isolated.metadata["background_removal_method"].endswith("v2")

    with Image.open(BytesIO(isolated.content)) as output:
        output.load()
        assert output.mode == "RGBA"
        alpha = output.getchannel("A")
        assert alpha.getpixel((0, 0)) == 0
        assert alpha.getpixel((output.width - 1, output.height - 1)) == 0
        assert alpha.getbbox() is not None
