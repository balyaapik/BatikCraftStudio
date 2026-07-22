"""Gambar sisipan mengambang: bisa digeser dulu sebelum melebur ke raster."""

from __future__ import annotations

import io

from PIL import Image

from batikcraft_studio.imaging.raster_document import RasterDocument
from batikcraft_studio.imaging.raster_insert import (
    centered_position,
    commit_floating_to_layer,
    point_in_floating,
    prepare_floating_image,
)


def _png(size, color):
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_prepare_memperkecil_agar_muat():
    floating = prepare_floating_image(_png((800, 400), (0, 0, 255, 255)), 200, 200)
    assert floating.width <= 200 and floating.height <= 200


def test_posisi_tengah():
    floating = prepare_floating_image(_png((40, 40), (255, 0, 0, 255)), 200, 200)
    assert centered_position(floating, 200, 200) == (80, 80)


def test_hit_test():
    floating = Image.new("RGBA", (40, 40))
    assert point_in_floating(85, 85, floating, (80, 80))
    assert not point_in_floating(10, 10, floating, (80, 80))
    assert not point_in_floating(120, 120, floating, (80, 80))


def test_commit_meleburkan_ke_layer():
    doc = RasterDocument(width=200, height=200)
    floating = prepare_floating_image(_png((40, 40), (255, 0, 0, 255)), 200, 200)

    box = commit_floating_to_layer(doc.active_layer, floating, (30, 30))

    assert box == (30, 30, 70, 70)
    assert doc.active_layer.image.getpixel((35, 35)) == (255, 0, 0, 255)
    assert doc.active_layer.image.getpixel((5, 5)) == (0, 0, 0, 0)


def test_commit_di_posisi_geser():
    """Setelah digeser, komit harus memakai posisi baru."""

    doc = RasterDocument(width=200, height=200)
    floating = prepare_floating_image(_png((20, 20), (0, 200, 0, 255)), 200, 200)

    commit_floating_to_layer(doc.active_layer, floating, (150, 150))

    assert doc.active_layer.image.getpixel((155, 155)) == (0, 200, 0, 255)
    assert doc.active_layer.image.getpixel((85, 85)) == (0, 0, 0, 0)
