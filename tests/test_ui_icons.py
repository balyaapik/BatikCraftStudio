from __future__ import annotations

import pytest
from PIL import Image

from batikcraft_studio.ui.icons import (
    FONT_AWESOME_LICENSE,
    FONT_AWESOME_VERSION,
    MASTER_ICON_SIZE,
    available_icons,
    default_icon_color,
    font_awesome_metadata,
    render_icon,
)


@pytest.mark.parametrize("name", available_icons())
def test_render_icon_produces_sharp_transparent_rgba_image(name: str) -> None:
    image = render_icon(name, size=24)

    assert image.mode == "RGBA"
    assert image.size == (24, 24)
    assert image.getbbox() is not None
    assert image.getchannel("A").getextrema() == (0, 255)


def test_render_icon_applies_requested_color_without_changing_alpha() -> None:
    red = render_icon("save", size=32, color="#E11D48")
    blue = render_icon("save", size=32, color="#2563EB")

    red_alpha = red.getchannel("A").tobytes()
    assert red_alpha == blue.getchannel("A").tobytes()

    opaque_index = red_alpha.index(255)
    opaque_pixel = red.getpixel((opaque_index % red.width, opaque_index // red.width))
    assert opaque_pixel == (225, 29, 72, 255)


def test_default_palette_uses_brighter_workspace_colors_on_dark_rail() -> None:
    assert default_icon_color("editor") != default_icon_color("editor", on_dark=True)
    assert default_icon_color("delete") == "#DC2626"
    assert default_icon_color("polygon_tool") == "#D97706"


def test_font_awesome_metadata_matches_embedded_and_custom_assets() -> None:
    metadata = font_awesome_metadata()

    assert metadata["font_awesome_version"] == FONT_AWESOME_VERSION
    assert metadata["license"] == FONT_AWESOME_LICENSE
    assert metadata["storage"] == "embedded-base85-alpha"
    assert metadata["master_size"] == MASTER_ICON_SIZE
    names = set(metadata["icons"]) | set(metadata["custom_icons"])
    assert names == set(available_icons())
    assert {
        "layer_add",
        "line_tool",
        "rectangle_tool",
        "ellipse_tool",
        "polygon_tool",
    } <= set(metadata["custom_icons"])
    with pytest.raises(TypeError):
        metadata["license"] = "changed"  # type: ignore[index]


def test_all_embedded_icon_data_decodes_without_external_archive() -> None:
    rendered = [render_icon(name, size=20) for name in available_icons()]

    assert len(rendered) == len(available_icons())
    assert all(image.getbbox() is not None for image in rendered)


def test_icon_source_can_be_resampled_for_different_ui_sizes() -> None:
    small = render_icon("editor", size=20)
    large = render_icon("editor", size=128)

    assert small.size == (20, 20)
    assert large.size == (128, 128)
    assert large.getbbox() is not None
    assert large.getchannel("A").getextrema() == (0, 255)


def test_render_icon_returns_independent_images() -> None:
    first = render_icon("open", size=20)
    second = render_icon("open", size=20)
    first.putpixel((0, 0), (255, 0, 0, 255))

    assert second.getpixel((0, 0)) != (255, 0, 0, 255)
    assert isinstance(second, Image.Image)


def test_render_icon_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown icon"):
        render_icon("missing")


def test_render_icon_rejects_too_small_size() -> None:
    with pytest.raises(ValueError, match="at least 12"):
        render_icon("save", size=8)


def test_render_icon_rejects_invalid_color() -> None:
    with pytest.raises(ValueError, match="Invalid icon color"):
        render_icon("save", color="not-a-color")
