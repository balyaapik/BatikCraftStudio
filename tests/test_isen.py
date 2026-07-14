from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from batikcraft_studio.imaging.isen import (
    ISEN_TYPES,
    IsenError,
    render_isen_cap,
    symmetry_placements,
    validate_cap_size,
)


@pytest.mark.parametrize("isen_type", ISEN_TYPES)
def test_render_isen_cap_returns_colored_transparent_png(isen_type: str) -> None:
    content = render_isen_cap(isen_type, color="#8B5A2B")

    with Image.open(BytesIO(content)) as source:
        source.load()
        image = source.convert("RGBA")

    assert image.size == (256, 256)
    assert image.getchannel("A").getextrema() == (0, 255)
    opaque_index = image.getchannel("A").tobytes().index(255)
    pixel = image.getpixel((opaque_index % image.width, opaque_index // image.width))
    assert pixel[:3] == (139, 90, 43)


def test_cermin_empat_returns_four_mirrored_placements() -> None:
    placements = symmetry_placements(
        (30, 40),
        canvas_width=200,
        canvas_height=120,
        susun="cermin_empat",
    )

    assert [(item.x, item.y) for item in placements] == [
        (30, 40),
        (170, 40),
        (30, 80),
        (170, 80),
    ]
    assert placements[1].mirror_x is True
    assert placements[2].mirror_y is True
    assert placements[3].mirror_x is True
    assert placements[3].mirror_y is True


def test_putar_4_rotates_around_center_kain() -> None:
    placements = symmetry_placements(
        (150, 100),
        canvas_width=200,
        canvas_height=200,
        susun="putar_4",
    )

    assert [(round(item.x), round(item.y)) for item in placements] == [
        (150, 100),
        (100, 150),
        (50, 100),
        (100, 50),
    ]
    assert [item.rotation_degrees for item in placements] == [0, 90, 180, 270]


def test_validate_cap_size_rejects_out_of_range_values() -> None:
    assert validate_cap_size(72) == 72
    with pytest.raises(IsenError, match="antara 8 dan 1024"):
        validate_cap_size(2)


def test_symmetry_rejects_position_outside_canvas() -> None:
    with pytest.raises(IsenError, match="di dalam"):
        symmetry_placements(
            (-1, 20),
            canvas_width=100,
            canvas_height=100,
            susun="tunggal",
        )
