from __future__ import annotations

import pytest
from PIL import Image

from batikcraft_studio.ui.icons import (
    FONT_AWESOME_LICENSE,
    FONT_AWESOME_VERSION,
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

    assert red.getchannel("A").tobytes() == blue.getchannel("A").tobytes()
    opaque_pixel = next(
        (pixel for pixel in red.getdata() if pixel[3] == 255),
        None,
    )
    assert opaque_pixel == (225, 29, 72, 255)


def test_default_palette_uses_brighter_workspace_colors_on_dark_rail() -> None:
    assert default_icon_color("editor") != default_icon_color("editor", on_dark=True)
    assert default_icon_color("delete") == "#DC2626"


def test_font_awesome_metadata_matches_bundled_assets() -> None:
    metadata = font_awesome_metadata()

    assert metadata["font_awesome_version"] == FONT_AWESOME_VERSION
    assert metadata["license"] == FONT_AWESOME_LICENSE
    assert set(metadata["icons"]) == set(available_icons())
    with pytest.raises(TypeError):
        metadata["license"] = "changed"  # type: ignore[index]


def test_icon_source_is_high_resolution_before_downsampling() -> None:
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
