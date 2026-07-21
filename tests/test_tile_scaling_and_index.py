"""Biaya render harus terbatas di semua level zoom dan semua jumlah objek."""

from __future__ import annotations

import pytest

from batikcraft_studio.imaging.cached_renderer import (
    _MAX_OBJECT_RENDER_PIXELS,
    _MAX_OBJECT_RENDER_PX,
    _clamp_render_size,
)
from batikcraft_studio.imaging.tile_cache import (
    MAX_TILE_SCREEN_PX,
    MIN_TILE_PROJECT_SIZE,
    TILE_SIZE,
    tile_project_size,
)


@pytest.mark.parametrize("zoom", [0.1, 0.25, 0.5, 1.0, 1.25, 2.0, 4.0, 8.0])
def test_sisi_tile_di_layar_selalu_terbatas(zoom):
    """Regresi: pada 800% satu tile dulu 4096 px (64 MB) dan render gagal."""

    size = tile_project_size(zoom)
    screen_px = size * zoom

    assert screen_px <= MAX_TILE_SCREEN_PX or size == MIN_TILE_PROJECT_SIZE
    assert size >= MIN_TILE_PROJECT_SIZE


def test_memori_tile_tidak_meledak_pada_zoom_tinggi():
    """Satu layar tile pada 800% harus sebanding dengan pada 100%."""

    def screen_bytes(zoom: float, view_w: int = 1600, view_h: int = 900) -> float:
        size = tile_project_size(zoom)
        tile_px = max(1, round(size * zoom))
        tiles = (view_w // tile_px + 3) * (view_h // tile_px + 3)
        return tiles * tile_px * tile_px * 4

    at_100 = screen_bytes(1.0)
    at_800 = screen_bytes(8.0)

    # Dulu rasionya ~24x (24 MB -> 576 MB).
    assert at_800 <= at_100 * 2


def test_zoom_kecil_memakai_tile_penuh():
    assert tile_project_size(1.0) == TILE_SIZE
    assert tile_project_size(0.25) == TILE_SIZE


def test_zoom_nol_atau_negatif_aman():
    assert tile_project_size(0.0) == TILE_SIZE
    assert tile_project_size(-1.0) == TILE_SIZE


@pytest.mark.parametrize(
    ("width", "height"),
    [(8192, 8192), (20000, 100), (100, 20000), (5000, 5000)],
)
def test_ukuran_render_objek_dibatasi(width, height):
    """Objek 1024 px pada 800% dulu minta 8192x8192 = 256 MB."""

    clamped_w, clamped_h = _clamp_render_size(width, height)

    assert clamped_w <= _MAX_OBJECT_RENDER_PX
    assert clamped_h <= _MAX_OBJECT_RENDER_PX
    assert clamped_w * clamped_h <= _MAX_OBJECT_RENDER_PIXELS
    assert clamped_w >= 1 and clamped_h >= 1


def test_ukuran_wajar_tidak_diubah():
    assert _clamp_render_size(1024, 1024) == (1024, 1024)
    assert _clamp_render_size(1, 1) == (1, 1)


def test_rasio_aspek_dipertahankan_saat_dibatasi():
    width, height = _clamp_render_size(16000, 8000)

    assert width == pytest.approx(height * 2, rel=0.02)


def test_layer_tanpa_objek_di_tile_dilewati():
    """Regresi: layer kosong dulu tetap dialokasikan dan dikomposisi.

    Biayanya ~0,9 ms per layer per tile — pada 20 layer dan 24 tile itu ~436 ms
    per render yang tidak menggambar apa pun. Inilah kenapa kanvas makin berat
    seiring bertambahnya layer/objek.
    """

    from batikcraft_studio.domain import (
        Layer,
        LayerKind,
        LayerObject,
        ObjectBounds,
        ObjectKind,
        Transform,
    )
    from batikcraft_studio.imaging.cached_renderer import CachedViewportRenderer

    jauh = LayerObject(
        name="jauh",
        kind=ObjectKind.SHAPE,
        transform=Transform(x=5000, y=5000),
        bounds=ObjectBounds(50, 50),
        properties={"shape": "rectangle"},
    )
    layer = Layer(name="Motif", kind=LayerKind.SHAPE, objects=[jauh])
    renderer = CachedViewportRenderer()

    surface = renderer._render_object_layer_tile(
        layer,
        {},
        proj_bounds=(0.0, 0.0, 512.0, 512.0),
        zoom_scale=1.0,
        region_left=0.0,
        region_top=0.0,
        out_size=(512, 512),
        project_revision=1,
    )

    assert surface is None


def test_layer_dengan_objek_di_tile_tetap_digambar():
    from batikcraft_studio.domain import (
        Layer,
        LayerKind,
        LayerObject,
        ObjectBounds,
        ObjectKind,
        Transform,
    )
    from batikcraft_studio.imaging.cached_renderer import CachedViewportRenderer

    dekat = LayerObject(
        name="dekat",
        kind=ObjectKind.SHAPE,
        transform=Transform(x=100, y=100),
        bounds=ObjectBounds(50, 50),
        properties={"shape": "rectangle"},
    )
    layer = Layer(name="Motif", kind=LayerKind.SHAPE, objects=[dekat])
    renderer = CachedViewportRenderer()

    surface = renderer._render_object_layer_tile(
        layer,
        {},
        proj_bounds=(0.0, 0.0, 512.0, 512.0),
        zoom_scale=1.0,
        region_left=0.0,
        region_top=0.0,
        out_size=(512, 512),
        project_revision=1,
    )

    assert surface is not None
    assert surface.size == (512, 512)
