"""Cache dekode + piramida mipmap untuk objek raster besar (hasil BatikBrew)."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from batikcraft_studio.imaging.tile_cache import (
    clear_decoded_asset_cache,
    decode_asset_once,
    decoded_asset_cache_stats,
    display_source,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_decoded_asset_cache()
    yield
    clear_decoded_asset_cache()


def _png(size: int = 1024) -> bytes:
    buffer = io.BytesIO()
    Image.effect_noise((size, size), 60).convert("RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


def test_dekode_hanya_sekali_untuk_bytes_yang_sama():
    content = _png(256)
    calls = 0

    def opener() -> Image.Image:
        nonlocal calls
        calls += 1
        return Image.open(io.BytesIO(content)).convert("RGBA")

    first = decode_asset_once(content, opener)
    second = decode_asset_once(content, opener)

    assert calls == 1
    assert first is second


def test_bytes_berbeda_didekode_terpisah():
    a, b = _png(64), _png(64)
    opener_a = lambda: Image.open(io.BytesIO(a)).convert("RGBA")  # noqa: E731
    opener_b = lambda: Image.open(io.BytesIO(b)).convert("RGBA")  # noqa: E731

    assert decode_asset_once(a, opener_a) is not decode_asset_once(b, opener_b)
    assert decoded_asset_cache_stats()["decoded_count"] == 2


def test_perkecilan_besar_memakai_level_mipmap():
    content = _png(1024)
    opener = lambda: Image.open(io.BytesIO(content)).convert("RGBA")  # noqa: E731

    source = display_source(content, opener, 200, 200)

    # 1024 -> 512 masih >= 2x target, jadi jauh lebih murah tanpa kehilangan mutu.
    assert source.size == (512, 512)
    assert decoded_asset_cache_stats()["decoded_levels"] == 2


def test_piramida_dipakai_ulang_bukan_dibangun_ulang():
    content = _png(1024)
    opener = lambda: Image.open(io.BytesIO(content)).convert("RGBA")  # noqa: E731

    first = display_source(content, opener, 200, 200)
    levels_after_first = decoded_asset_cache_stats()["decoded_levels"]
    second = display_source(content, opener, 200, 200)

    assert first is second
    assert decoded_asset_cache_stats()["decoded_levels"] == levels_after_first


def test_pembesaran_memakai_gambar_resolusi_penuh():
    content = _png(256)
    opener = lambda: Image.open(io.BytesIO(content)).convert("RGBA")  # noqa: E731

    source = display_source(content, opener, 2048, 2048)

    assert source.size == (256, 256)


def test_level_tidak_pernah_lebih_kecil_dari_target():
    content = _png(1024)
    opener = lambda: Image.open(io.BytesIO(content)).convert("RGBA")  # noqa: E731

    for target in (16, 64, 100, 200, 400, 700, 1024):
        source = display_source(content, opener, target, target)
        assert source.width >= target
        assert source.height >= target


def test_clear_membebaskan_memori():
    content = _png(512)
    opener = lambda: Image.open(io.BytesIO(content)).convert("RGBA")  # noqa: E731

    display_source(content, opener, 100, 100)
    assert decoded_asset_cache_stats()["decoded_bytes"] > 0

    clear_decoded_asset_cache()

    assert decoded_asset_cache_stats()["decoded_bytes"] == 0
    assert decoded_asset_cache_stats()["decoded_count"] == 0


def test_gambar_raksasa_tidak_mengusir_isi_cache():
    from batikcraft_studio.imaging import tile_cache

    small = _png(64)
    opener_small = lambda: Image.open(io.BytesIO(small)).convert("RGBA")  # noqa: E731
    decode_asset_once(small, opener_small)

    huge_content = b"huge"
    huge = Image.new("RGBA", (256, 256))
    monster_limit = tile_cache._DECODED_ASSET_LIMIT_BYTES
    try:
        tile_cache._DECODED_ASSET_LIMIT_BYTES = 1024
        decode_asset_once(huge_content, lambda: huge)
    finally:
        tile_cache._DECODED_ASSET_LIMIT_BYTES = monster_limit

    # Aset kecil tetap ada; yang raksasa tidak ikut disimpan.
    assert decoded_asset_cache_stats()["decoded_count"] == 1
