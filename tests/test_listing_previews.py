"""Preview estetis untuk listing pustaka aset dan model di BatikCraftWeb."""

from __future__ import annotations

import inspect
import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from batikcraft_studio.assets.preview import (
    compose_collage_preview,
    extract_model_pack_preview,
)


def _png(color: tuple[int, int, int, int]) -> bytes:
    image = Image.new("RGBA", (64, 64), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_collage_preview_composes_square_grid() -> None:
    collage = compose_collage_preview(
        [_png((200, 50, 50, 255)), _png((50, 200, 50, 255)), _png((50, 50, 200, 255))]
    )
    with Image.open(BytesIO(collage)) as image:
        image.load()
        assert image.width == 768
        assert image.height > 0


def test_collage_preview_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        compose_collage_preview([])


def test_model_pack_preview_extraction(tmp_path: Path) -> None:
    package = tmp_path / "model.batikmodel"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"model": {"name": "M"}}))
        archive.writestr("preview/sample-01.png", _png((10, 20, 30, 255)))
    assert extract_model_pack_preview(package) is not None
    assert extract_model_pack_preview(tmp_path / "tidak-ada.batikmodel") is None


def test_dialogs_require_and_display_previews() -> None:
    from batikcraft_studio.ui import asset_pack_studio_dialog, web_marketplace_dialogs

    studio = inspect.getsource(asset_pack_studio_dialog)
    assert "compose_collage_preview" in studio
    assert "Ganti Gambar Preview…" in studio

    market = inspect.getsource(web_marketplace_dialogs)
    assert "Preview diperlukan" in market  # preview model wajib
    assert "_suggest_pack_preview" in market
