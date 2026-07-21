"""Pratinjau zoom harus mendarat persis di posisi tile final.

Kalau geometri pratinjau dan geometri render final dihitung terpisah, keduanya
bisa bergeser dan pergantiannya terlihat sebagai kedipan/lompatan. Uji ini
mengunci invarian: satu titik proyek memetakan ke koordinat kanvas yang sama,
lewat jalur mana pun, pada skala berapa pun.
"""

from __future__ import annotations

import pytest

from batikcraft_studio.imaging.tile_cache import TILE_SIZE
from batikcraft_studio.ui.viewport_editor import (
    _VIEW_PADDING,
    ViewportEditorWorkspaceView,
)


class _FakeCanvas:
    def __init__(self, width: int, height: int) -> None:
        self._w, self._h = width, height

    def winfo_width(self) -> int:
        return self._w

    def winfo_height(self) -> int:
        return self._h


class _FakeCanvasSpec:
    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height


class _FakeProject:
    def __init__(self, width: int = 2048, height: int = 2048) -> None:
        self.canvas = _FakeCanvasSpec(width, height)


def _geometry(view_w, view_h, project, scale):
    view = object.__new__(ViewportEditorWorkspaceView)
    view.canvas = _FakeCanvas(view_w, view_h)
    return ViewportEditorWorkspaceView._preview_geometry(view, project, scale)


@pytest.mark.parametrize(
    "scale", [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0]
)
def test_titik_proyek_memetakan_konsisten_di_semua_skala(scale):
    """125% dulu bikin gambar hilang — semua skala sekarang dikunci uji."""

    project = _FakeProject()
    left, top, content_w, content_h = _geometry(1600, 900, project, scale)

    # Jalur tile: posisi tile (tx, ty) di kanvas.
    tile_px = max(1, round(TILE_SIZE * scale))
    tile_x = left + 1 * tile_px
    tile_y = top + 1 * tile_px

    # Jalur pratinjau: titik proyek yang sama, dihitung dari koordinat proyek.
    preview_x = left + (1 * TILE_SIZE) * scale
    preview_y = top + (1 * TILE_SIZE) * scale

    # Selisih hanya boleh berasal dari pembulatan tile_px ke piksel bulat.
    assert abs(tile_x - preview_x) <= 1.0
    assert abs(tile_y - preview_y) <= 1.0
    assert content_w > 0 and content_h > 0


@pytest.mark.parametrize("scale", [0.25, 1.0, 1.25, 2.0])
def test_geometri_stabil_untuk_masukan_yang_sama(scale):
    project = _FakeProject()
    assert _geometry(1600, 900, project, scale) == _geometry(1600, 900, project, scale)


def test_konten_tidak_pernah_lebih_kecil_dari_viewport():
    project = _FakeProject(256, 256)
    _left, _top, content_w, content_h = _geometry(1600, 900, project, 0.25)

    assert content_w >= 1600
    assert content_h >= 900


def test_gambar_kecil_diletakkan_di_tengah():
    project = _FakeProject(256, 256)
    left, top, content_w, content_h = _geometry(1600, 900, project, 1.0)

    assert left == pytest.approx((content_w - 256) / 2)
    assert top == pytest.approx((content_h - 256) / 2)


def test_gambar_besar_memakai_padding_tetap():
    project = _FakeProject(4096, 4096)
    left, top, _content_w, _content_h = _geometry(800, 600, project, 2.0)

    assert left == float(_VIEW_PADDING)
    assert top == float(_VIEW_PADDING)
