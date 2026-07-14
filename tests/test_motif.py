from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from batikcraft_studio.imaging.motif import (
    DEFAULT_MOTIF_ISEN,
    MOTIF_TYPES,
    MotifError,
    motif_description,
    render_motif_cap,
)


@pytest.mark.parametrize("motif_type", MOTIF_TYPES)
def test_render_motif_cap_builds_transparent_complete_motif(motif_type: str) -> None:
    content = render_motif_cap(
        motif_type,
        motif_color="#4E2A1E",
        isen_color="#8B5A2B",
        auto_isen=True,
    )

    with Image.open(BytesIO(content)) as source:
        source.load()
        image = source.convert("RGBA")

    alpha = image.getchannel("A")
    assert image.size == (512, 512)
    assert alpha.getextrema() == (0, 255)
    assert alpha.getbbox() is not None
    assert sum(value > 0 for value in alpha.tobytes()) > 6000


@pytest.mark.parametrize("motif_type", MOTIF_TYPES)
def test_automatic_isen_adds_detail_inside_motif(motif_type: str) -> None:
    with_isen = render_motif_cap(
        motif_type,
        motif_color="#4E2A1E",
        isen_color="#8B5A2B",
        auto_isen=True,
    )
    without_isen = render_motif_cap(
        motif_type,
        motif_color="#4E2A1E",
        isen_color="#8B5A2B",
        auto_isen=False,
    )

    with Image.open(BytesIO(with_isen)) as source:
        filled_alpha = source.convert("RGBA").getchannel("A").tobytes()
    with Image.open(BytesIO(without_isen)) as source:
        outline_alpha = source.convert("RGBA").getchannel("A").tobytes()

    assert sum(value > 0 for value in filled_alpha) > sum(value > 0 for value in outline_alpha)


def test_motif_description_uses_default_isen() -> None:
    assert DEFAULT_MOTIF_ISEN["kawung"] == "cecek_sawut"
    assert motif_description("kawung") == "Kawung dengan isen Cecek Sawut"


def test_render_motif_rejects_unknown_template() -> None:
    with pytest.raises(MotifError, match="Motif pokok tidak didukung"):
        render_motif_cap(
            "tidak_ada",
            motif_color="#4E2A1E",
            isen_color="#8B5A2B",
        )
