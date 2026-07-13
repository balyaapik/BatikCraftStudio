from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from batikcraft_studio.domain import CanvasSpec, Layer, Project, Transform
from batikcraft_studio.imaging import (
    MissingRasterAssetError,
    RasterImageError,
    normalize_raster_image,
    render_project_preview,
    transformed_layer_bounds,
)


def _image_bytes(
    *,
    size: tuple[int, int] = (20, 10),
    color: tuple[int, ...] = (220, 30, 20, 255),
    image_format: str = "PNG",
) -> bytes:
    mode = "RGBA" if len(color) == 4 and image_format != "JPEG" else "RGB"
    image = Image.new(mode, size, color[: len(mode)])
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_normalize_jpeg_returns_rgba_png() -> None:
    result = normalize_raster_image(
        _image_bytes(color=(10, 120, 230), image_format="JPEG")
    )

    assert result.source_format == "JPEG"
    assert result.width == 20
    assert result.height == 10
    assert result.content.startswith(b"\x89PNG")
    with Image.open(BytesIO(result.content)) as image:
        assert image.mode == "RGBA"
        assert image.size == (20, 10)


def test_normalize_rejects_empty_and_invalid_content() -> None:
    with pytest.raises(RasterImageError, match="must not be empty"):
        normalize_raster_image(b"")
    with pytest.raises(RasterImageError, match="not a readable"):
        normalize_raster_image(b"not-an-image")


def test_renderer_composites_visible_layer_at_project_center() -> None:
    project = Project.create(
        "Preview",
        "Tester",
        canvas=CanvasSpec(width=100, height=80, background_color="#FFFFFF"),
    )
    project.add_layer(
        Layer(
            name="Red rectangle",
            asset_ref="assets/red.png",
            transform=Transform(x=50, y=40),
            properties={"pixel_width": 20, "pixel_height": 10},
        )
    )

    rendered = render_project_preview(
        project,
        {"assets/red.png": _image_bytes()},
        max_width=100,
        max_height=80,
    )

    assert rendered.scale == 1.0
    assert rendered.image.size == (100, 80)
    red, green, blue, alpha = rendered.image.getpixel((50, 40))
    assert red > 200
    assert green < 60
    assert blue < 60
    assert alpha == 255


def test_renderer_skips_hidden_layer() -> None:
    project = Project.create(
        "Preview",
        "Tester",
        canvas=CanvasSpec(width=100, height=80, background_color="#FFFFFF"),
    )
    project.add_layer(
        Layer(
            name="Hidden",
            asset_ref="assets/red.png",
            visible=False,
            transform=Transform(x=50, y=40),
            properties={"pixel_width": 20, "pixel_height": 10},
        )
    )

    rendered = render_project_preview(
        project,
        {"assets/red.png": _image_bytes()},
        max_width=100,
        max_height=80,
    )

    assert rendered.image.getpixel((50, 40)) == (255, 255, 255, 255)


def test_renderer_rejects_missing_visible_asset() -> None:
    project = Project.create("Preview", "Tester")
    project.add_layer(
        Layer(
            name="Missing",
            asset_ref="assets/missing.png",
            properties={"pixel_width": 20, "pixel_height": 10},
        )
    )

    with pytest.raises(MissingRasterAssetError, match="missing asset"):
        render_project_preview(project, {}, max_width=200, max_height=200)


def test_transformed_bounds_account_for_rotation() -> None:
    layer = Layer(
        name="Rotated",
        transform=Transform(x=50, y=40, rotation_degrees=90, scale_x=2, scale_y=1),
        properties={"pixel_width": 20, "pixel_height": 10},
    )

    left, top, right, bottom = transformed_layer_bounds(layer)

    assert left == pytest.approx(45)
    assert right == pytest.approx(55)
    assert top == pytest.approx(20)
    assert bottom == pytest.approx(60)
