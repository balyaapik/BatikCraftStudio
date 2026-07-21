"""Pengecatan bertahap terurut dari kursor (pendekatan Inkscape).

Inkscape mengecat ulang bagian yang "tidak bersih" secara bertahap, "each
outwards from the mouse", dan menyerahkan kendali ke main loop di sela-selanya.
Total kerjanya sama; yang berubah adalah urutan dan kapan hasilnya tampil.
"""

from __future__ import annotations

import math


def _order_from_focus(
    coords: list[tuple[int, int]], focus_tx: float, focus_ty: float
) -> list[tuple[int, int]]:
    return sorted(
        coords,
        key=lambda c: (c[0] + 0.5 - focus_tx) ** 2 + (c[1] + 0.5 - focus_ty) ** 2,
    )


def test_tile_terdekat_kursor_didahulukan():
    coords = [(x, y) for y in range(5) for x in range(5)]

    ordered = _order_from_focus(coords, 2.5, 2.5)

    assert ordered[0] == (2, 2)


def test_urutan_membesar_dari_kursor_ke_luar():
    coords = [(x, y) for y in range(5) for x in range(5)]

    ordered = _order_from_focus(coords, 0.5, 0.5)
    jarak = [
        math.hypot(x + 0.5 - 0.5, y + 0.5 - 0.5) for x, y in ordered
    ]

    assert jarak == sorted(jarak)


def test_semua_tile_tetap_dirender():
    """Mengurutkan tidak boleh menghilangkan satu tile pun."""

    coords = [(x, y) for y in range(6) for x in range(4)]

    ordered = _order_from_focus(coords, 1.5, 3.5)

    assert sorted(ordered) == sorted(coords)
    assert len(ordered) == len(coords)


def test_fokus_di_luar_layar_tetap_menghasilkan_urutan_sah():
    coords = [(x, y) for y in range(3) for x in range(3)]

    ordered = _order_from_focus(coords, -10.0, 50.0)

    assert sorted(ordered) == sorted(coords)


def test_kursor_di_pojok_mendahulukan_pojok_itu():
    coords = [(x, y) for y in range(4) for x in range(4)]

    ordered = _order_from_focus(coords, 3.5, 3.5)

    assert ordered[0] == (3, 3)
    assert ordered[-1] == (0, 0)
