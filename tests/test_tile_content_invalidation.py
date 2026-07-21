"""Menggambar satu objek tidak boleh membatalkan seluruh cache tile.

Dulu ``TileCacheKey`` memakai revisi GLOBAL proyek, jadi satu goresan pena
mengubah revisi dan setiap tile kehilangan cache-nya — kanvas terasa dirender
ulang dari nol setiap kali menggambar atau zoom.
"""

from __future__ import annotations

import pytest

from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Transform,
)
from batikcraft_studio.imaging.cached_renderer import (
    _LayerSpatialIndex,
    _object_signature,
)


def _object(name: str, x: float, y: float, size: float = 80.0) -> LayerObject:
    return LayerObject(
        name=name,
        kind=ObjectKind.SHAPE,
        transform=Transform(x=x, y=y),
        bounds=ObjectBounds(size, size),
        properties={"shape": "rectangle"},
    )


def _layer(objects: list[LayerObject]) -> Layer:
    return Layer(name="Motif", kind=LayerKind.SHAPE, objects=objects)


def test_tanda_tangan_berubah_saat_objek_dipindah():
    before = _object("a", 100, 100)
    after = LayerObject(
        name=before.name,
        kind=before.kind,
        object_id=before.object_id,
        transform=Transform(x=900, y=900),
        bounds=before.bounds,
        properties=dict(before.properties),
    )

    assert _object_signature(before) != _object_signature(after)


def test_tanda_tangan_stabil_untuk_objek_yang_tidak_berubah():
    item = _object("a", 100, 100)
    twin = LayerObject(
        name=item.name,
        kind=item.kind,
        object_id=item.object_id,
        transform=Transform(x=100, y=100),
        bounds=item.bounds,
        properties=dict(item.properties),
    )

    assert _object_signature(item) == _object_signature(twin)


@pytest.mark.parametrize("field", ["opacity", "visible"])
def test_perubahan_tampilan_terdeteksi(field):
    item = _object("a", 100, 100)
    changed = LayerObject(
        name=item.name,
        kind=item.kind,
        object_id=item.object_id,
        transform=item.transform,
        bounds=item.bounds,
        properties=dict(item.properties),
        **{field: 0.5 if field == "opacity" else False},
    )

    assert _object_signature(item) != _object_signature(changed)


def test_indeks_hanya_mengembalikan_objek_yang_bersinggungan():
    near = _object("dekat", 100, 100)
    far = _object("jauh", 3000, 3000)
    index = _LayerSpatialIndex(_layer([near, far]))

    candidates = index.candidates((0.0, 0.0, 512.0, 512.0))

    assert 0 in candidates
    assert 1 not in candidates


def test_indeks_mempertahankan_urutan_gambar():
    objects = [_object(f"o{i}", 100 + i, 100 + i) for i in range(6)]
    index = _LayerSpatialIndex(_layer(objects))

    candidates = index.candidates((0.0, 0.0, 512.0, 512.0))

    assert candidates == sorted(candidates)
    assert len(candidates) == len(objects)


def test_objek_tak_terlihat_tidak_masuk_indeks():
    hidden = LayerObject(
        name="tersembunyi",
        kind=ObjectKind.SHAPE,
        transform=Transform(x=100, y=100),
        bounds=ObjectBounds(80, 80),
        visible=False,
        properties={"shape": "rectangle"},
    )
    index = _LayerSpatialIndex(_layer([hidden]))

    assert index.candidates((0.0, 0.0, 512.0, 512.0)) == []


def test_objek_sangat_besar_selalu_ikut_dipertimbangkan():
    """Objek raksasa disimpan terpisah supaya indeks tidak meledak."""

    huge = _object("raksasa", 5000, 5000, size=20000)
    index = _LayerSpatialIndex(_layer([huge]))

    assert index.oversized == [0]
    # Tetap muncul sebagai kandidat di tile mana pun.
    assert 0 in index.candidates((0.0, 0.0, 512.0, 512.0))


def test_bounds_dihitung_sekali_dan_dipakai_ulang():
    objects = [_object(f"o{i}", 100 * i, 100 * i) for i in range(10)]
    index = _LayerSpatialIndex(_layer(objects))

    assert len(index.bounds) == len(objects)
    assert len(index.signatures) == len(objects)


def test_indeks_dibangun_ulang_saat_daftar_objek_berbeda():
    """Regresi: patch interaksi menyaring objek dan membuat Layer baru.

    Posisi di dalam indeks hanya sahih untuk daftar objek yang membangunnya.
    Tanpa pemeriksaan identitas, indeks lama akan menunjuk objek yang salah.
    """

    from batikcraft_studio.imaging.cached_renderer import CachedViewportRenderer

    a = _object("a", 100, 100)
    b = _object("b", 200, 200)
    penuh = _layer([a, b])
    disaring = Layer(name=penuh.name, kind=penuh.kind, layer_id=penuh.layer_id, objects=[a])

    renderer = CachedViewportRenderer()
    index_penuh = renderer._get_layer_index(penuh, 1)
    index_disaring = renderer._get_layer_index(disaring, 1)

    assert index_penuh is not index_disaring
    assert len(index_penuh.bounds) == 2
    assert len(index_disaring.bounds) == 1
