"""Cache bitmap hidup bersama untuk lapis canting raster kanvas utama."""

from __future__ import annotations

from PIL import Image

from batikcraft_studio.imaging import live_bitmap_store


def _fresh():
    live_bitmap_store.clear()


def test_put_get():
    _fresh()
    image = Image.new("RGBA", (10, 10))
    live_bitmap_store.put("assets/a.png", image)
    assert live_bitmap_store.get("assets/a.png") is image


def test_get_kosong_none():
    _fresh()
    assert live_bitmap_store.get("assets/x.png") is None
    assert live_bitmap_store.get(None) is None


def test_discard():
    _fresh()
    live_bitmap_store.put("a", Image.new("RGBA", (2, 2)))
    live_bitmap_store.discard("a")
    assert live_bitmap_store.get("a") is None


def test_eviksi_lru():
    _fresh()
    for i in range(40):
        live_bitmap_store.put(f"k{i}", Image.new("RGBA", (2, 2)))
    assert live_bitmap_store.get("k0") is None      # tertua terusir
    assert live_bitmap_store.get("k39") is not None  # terbaru tetap


def test_clear():
    _fresh()
    live_bitmap_store.put("a", Image.new("RGBA", (2, 2)))
    live_bitmap_store.clear()
    assert live_bitmap_store.get("a") is None
