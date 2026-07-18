"""Regresi: delta drag multi-objek dihitung dari layar mentah / zoom.

Render eksklusi di awal gesture dapat menggeser scroll/offset canvas sehingga
pemetaan screen->project berubah di tengah drag. Delta berbasis layar mentah
kebal terhadap pergeseran itu.
"""

from __future__ import annotations

from batikcraft_studio.ui.multi_object_editor import _MultiMoveDrag


def test_project_delta_uses_screen_delta_divided_by_scale() -> None:
    drag = _MultiMoveDrag(start_project=(50.0, 50.0), start_screen=(100, 80), scale=2.0)
    # Pemetaan project berubah drastis (mis. scroll bergeser setelah render
    # eksklusi); fallback point yang "melenceng" tidak boleh dipakai.
    delta = drag.project_delta(130, 80, fallback_point=(999.0, -999.0))
    assert delta == (15.0, 0.0)


def test_project_delta_falls_back_to_project_points_without_screen_start() -> None:
    drag = _MultiMoveDrag(start_project=(50.0, 40.0))
    assert drag.project_delta(0, 0, fallback_point=(80.0, 45.0)) == (30.0, 5.0)
    assert drag.project_delta(0, 0, fallback_point=None) is None


def test_project_delta_ignores_non_positive_scale() -> None:
    drag = _MultiMoveDrag(start_project=(0.0, 0.0), start_screen=(0, 0), scale=0.0)
    assert drag.project_delta(10, 10, fallback_point=(3.0, 4.0)) == (3.0, 4.0)
