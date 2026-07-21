"""Batas zoom antarmuka: maksimum 150%."""

from __future__ import annotations

from batikcraft_studio.ui.viewport_editor import (
    _MAX_ZOOM,
    _MIN_ZOOM,
    _ZOOM_LEVELS,
)


def test_zoom_maksimum_150_persen():
    assert _MAX_ZOOM == 1.50


def test_daftar_level_berhenti_di_maksimum():
    assert max(_ZOOM_LEVELS) == _MAX_ZOOM
    assert all(level <= _MAX_ZOOM for level in _ZOOM_LEVELS)


def test_daftar_level_dimulai_dari_minimum():
    assert min(_ZOOM_LEVELS) == _MIN_ZOOM
    assert all(level >= _MIN_ZOOM for level in _ZOOM_LEVELS)


def test_level_menaik_dan_unik():
    assert list(_ZOOM_LEVELS) == sorted(set(_ZOOM_LEVELS))


def test_level_penting_tetap_tersedia():
    for level in (0.25, 0.50, 1.0, 1.25, 1.50):
        assert level in _ZOOM_LEVELS
