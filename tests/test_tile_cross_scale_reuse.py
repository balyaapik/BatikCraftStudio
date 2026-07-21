"""Melewati batas bucket zoom tidak boleh terasa seperti render ulang total.

Bucket zoom adalah (0.125, 0.25, 0.5, 1.0, ...). Menyeberanginya mengubah kunci
cache SETIAP tile dan SETIAP objek sekaligus, jadi semuanya digambar ulang.
Tile dengan isi sama dari zoom sebelumnya dipakai sebagai tampilan sementara
supaya layar tidak pernah kosong.
"""

from __future__ import annotations

import pytest
from PIL import Image

from batikcraft_studio.imaging.tile_cache import TileCache, TileCacheKey


def _key(bucket: float, *, tile_size: int = 512, tx: int = 0, revision: int = 1):
    return TileCacheKey(
        project_revision=revision,
        zoom_bucket=bucket,
        tile_size=tile_size,
        tile_x=tx,
        tile_y=0,
        canvas_background="#ffffff",
        visibility_revision=0,
    )


def test_tile_isi_sama_ditemukan_pada_skala_lain():
    cache = TileCache(max_bytes=50 * 1024 * 1024)
    cache.put(_key(0.5), Image.new("RGBA", (256, 256)))

    found = cache.find_any_scale(_key(1.0))

    assert found is not None
    assert found.size == (256, 256)


def test_resolusi_tertinggi_yang_dipilih():
    cache = TileCache(max_bytes=50 * 1024 * 1024)
    cache.put(_key(0.5), Image.new("RGBA", (256, 256)))
    cache.put(_key(1.0), Image.new("RGBA", (512, 512)))

    assert cache.find_any_scale(_key(2.0)).size == (512, 512)


def test_isi_berbeda_tidak_dipakai_ulang():
    """Kalau objeknya berubah, tile lama TIDAK boleh dipakai."""

    cache = TileCache(max_bytes=50 * 1024 * 1024)
    cache.put(_key(0.5, revision=1), Image.new("RGBA", (256, 256)))

    assert cache.find_any_scale(_key(1.0, revision=2)) is None


def test_posisi_tile_berbeda_tidak_tertukar():
    cache = TileCache(max_bytes=50 * 1024 * 1024)
    cache.put(_key(1.0, tx=0), Image.new("RGBA", (512, 512)))

    assert cache.find_any_scale(_key(1.0, tx=7)) is None


def test_indeks_bersih_setelah_eviksi():
    """Kunci yang sudah diusir tidak boleh tertinggal di indeks sekunder."""

    cache = TileCache(max_bytes=1024)
    cache.put(_key(1.0), Image.new("RGBA", (512, 512)))
    cache.put(_key(0.5, tx=5), Image.new("RGBA", (512, 512)))

    assert cache.find_any_scale(_key(1.0)) is None
    total_indexed = sum(len(keys) for keys in cache._by_content.values())
    assert total_indexed == len(cache._store)


def test_clear_mengosongkan_indeks():
    cache = TileCache(max_bytes=50 * 1024 * 1024)
    cache.put(_key(1.0), Image.new("RGBA", (512, 512)))

    cache.clear()

    assert cache._by_content == {}
    assert cache.find_any_scale(_key(1.0)) is None


@pytest.mark.parametrize("bucket", [0.125, 0.25, 0.5, 1.0])
def test_semua_bucket_saling_dapat_dipakai_ulang(bucket):
    cache = TileCache(max_bytes=50 * 1024 * 1024)
    cache.put(_key(bucket), Image.new("RGBA", (128, 128)))

    for other in (0.125, 0.25, 0.5, 1.0):
        if other == bucket:
            continue
        assert cache.find_any_scale(_key(other)) is not None
