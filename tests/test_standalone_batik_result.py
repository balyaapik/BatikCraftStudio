"""Hasil batifikasi harus berupa gambar tunggal, dan latar foto dibersihkan dulu."""

from __future__ import annotations

import inspect
from io import BytesIO

from PIL import Image, ImageDraw

from batikcraft_studio.imaging.background_removal import (
    has_transparent_background,
    remove_background,
)


def _photo_with_background() -> bytes:
    image = Image.new("RGB", (192, 192), (205, 205, 210))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((70, 45, 125, 170), radius=14, fill=(120, 70, 40))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_background_is_removed_but_object_kept() -> None:
    content, removed = remove_background(_photo_with_background())
    assert removed is True

    result = Image.open(BytesIO(content))
    alpha = result.getchannel("A")
    assert alpha.getpixel((5, 5)) == 0          # sudut = latar, transparan
    assert alpha.getpixel((97, 110)) == 255     # badan objek tetap utuh
    assert has_transparent_background(result) is True


def test_transparent_assets_are_left_untouched() -> None:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((8, 8, 56, 56), fill=(90, 40, 20, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    original = buffer.getvalue()

    content, removed = remove_background(original)
    assert removed is False
    assert content == original


def test_object_coloured_like_background_survives() -> None:
    """Warna objek yang mirip latar tidak boleh ikut terhapus selama tidak
    tersambung ke tepi gambar."""

    image = Image.new("RGB", (128, 128), (240, 240, 240))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 88, 88), fill=(60, 60, 60))
    draw.rectangle((55, 55, 73, 73), fill=(240, 240, 240))  # lubang sewarna latar
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    content, removed = remove_background(buffer.getvalue())
    assert removed is True
    alpha = Image.open(BytesIO(content)).getchannel("A")
    assert alpha.getpixel((64, 64)) == 255  # bagian dalam objek tetap ada


def test_generated_result_is_a_plain_standalone_image() -> None:
    """Hasil disisipkan sebagai RASTER, bukan komponen MOTIF terikat, sehingga
    dapat disalin/ditempel seperti gambar canvas biasa."""

    from batikcraft_studio.application import pretrained_ai_batification_session as module

    source = inspect.getsource(module)
    assert "output_kind = ObjectKind.RASTER" in source
    assert "kind=output_kind," in source
    assert '"standalone_image": True' in source
    assert '"asset_category": "ornamen"' in source


def test_source_photo_background_removed_before_generation() -> None:
    from batikcraft_studio.application import pretrained_ai_batification_session as module

    source = inspect.getsource(module)
    assert "_without_background(source_content)" in source
    assert "remove_background" in source
