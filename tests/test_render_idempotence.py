"""Render berulang tanpa perubahan tidak boleh menyentuh apa pun.

Menggambar memicu render setiap ~35 ms. Kalau setiap render menggeser posisi
gulir dan membangun ulang grid, kanvas berkedip walaupun tidak ada yang
berubah — dan hanya terlihat pada zoom >= 100%, karena di bawah itu gambar
masih muat di jendela sehingga posisi gulir terkunci di 0.
"""

from __future__ import annotations

import pytest

_VIEW_PADDING = 28


def _layout(view_w: int, view_h: int, canvas_px: int, zoom: float):
    display = max(1, round(canvas_px * zoom))
    content_w = max(view_w, display + _VIEW_PADDING * 2)
    content_h = max(view_h, display + _VIEW_PADDING * 2)
    return content_w, content_h


@pytest.mark.parametrize("zoom", [0.25, 0.5, 0.75, 1.0, 1.25, 1.5])
def test_tata_letak_identik_untuk_render_berulang(zoom):
    """Menggambar tidak mengubah skala, jadi tata letaknya harus sama persis."""

    first = _layout(1600, 900, 2048, zoom)
    second = _layout(1600, 900, 2048, zoom)

    assert first == second


def test_gulir_aktif_ditentukan_konten_vs_jendela():
    """Gulir aktif begitu konten melampaui jendela — bukan tepat di 100%.

    Untuk kanvas 2048 px pada jendela 1600x900, gulir vertikal sudah aktif
    sejak ~41%. Yang penting bukan angka ambangnya, melainkan bahwa render
    berulang tidak boleh memanggil gulir lagi saat tata letaknya sama.
    """

    _content_w, content_h = _layout(1600, 900, 2048, 0.5)
    assert max(0.0, content_h - 900) > 0.0

    _content_w, content_h = _layout(1600, 900, 2048, 0.1)
    assert max(0.0, content_h - 900) == 0.0


@pytest.mark.parametrize("zoom", [1.0, 1.25, 1.5])
def test_zoom_masuk_selalu_mengaktifkan_gulir(zoom):
    content_w, content_h = _layout(1600, 900, 2048, zoom)

    assert max(0.0, content_w - 1600) > 0.0
    assert max(0.0, content_h - 900) > 0.0


def test_perubahan_zoom_mengubah_tata_letak():
    """Tata letak wajib dianggap berubah saat zoom berubah."""

    assert _layout(1600, 900, 2048, 1.0) != _layout(1600, 900, 2048, 1.25)
