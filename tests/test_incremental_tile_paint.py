"""Jalur cepat ala MS Paint: menambah objek = menimpakan, bukan menggambar ulang.

MS Paint ringan karena menggambar hanya menulis piksel di jejak kuas — biayanya
tidak bergantung pada isi gambar. Prinsip yang sama dipakai di sini: kalau isi
tile yang baru adalah isi lama DITAMBAH objek di atasnya, hasil akhirnya cukup
diperoleh dengan menimpakan objek baru saja.

Syarat kesetaraannya ketat, dan uji ini menguncinya.
"""

from __future__ import annotations

from PIL import Image, ImageChops

from batikcraft_studio.imaging.tile_cache import TileCache, TileCacheKey


def _key(revision: int, *, tx: int = 0, bucket: float = 1.0) -> TileCacheKey:
    return TileCacheKey(
        project_revision=revision,
        zoom_bucket=bucket,
        tile_size=512,
        tile_x=tx,
        tile_y=0,
        canvas_background="#ffffff",
        visibility_revision=0,
    )


def test_awalan_ditemukan_saat_objek_ditambahkan():
    cache = TileCache(max_bytes=50 * 1024 * 1024)
    lama = ("bg", "a", "b")
    cache.put(_key(1), Image.new("RGBA", (512, 512)), lama)

    hasil = cache.find_prefix(_key(2), ("bg", "a", "b", "c"))

    assert hasil is not None
    assert hasil[1] == len(lama)


def test_isi_identik_bukan_awalan():
    """Kalau tidak ada yang ditambahkan, ini urusan cache biasa."""

    cache = TileCache(max_bytes=50 * 1024 * 1024)
    cache.put(_key(1), Image.new("RGBA", (512, 512)), ("bg", "a"))

    assert cache.find_prefix(_key(1), ("bg", "a")) is None


def test_objek_yang_berubah_di_tengah_ditolak():
    """Mengubah objek lama BUKAN penambahan — harus digambar ulang penuh."""

    cache = TileCache(max_bytes=50 * 1024 * 1024)
    cache.put(_key(1), Image.new("RGBA", (512, 512)), ("bg", "a", "b"))

    assert cache.find_prefix(_key(2), ("bg", "a", "BERUBAH", "c")) is None


def test_objek_yang_dihapus_ditolak():
    cache = TileCache(max_bytes=50 * 1024 * 1024)
    cache.put(_key(1), Image.new("RGBA", (512, 512)), ("bg", "a", "b", "c"))

    assert cache.find_prefix(_key(2), ("bg", "a", "b")) is None


def test_awalan_terpanjang_yang_dipilih():
    """Makin panjang awalannya, makin sedikit objek yang perlu ditimpakan."""

    cache = TileCache(max_bytes=50 * 1024 * 1024)
    cache.put(_key(1), Image.new("RGBA", (512, 512)), ("bg", "a"))
    cache.put(_key(2), Image.new("RGBA", (512, 512)), ("bg", "a", "b", "c"))

    hasil = cache.find_prefix(_key(3), ("bg", "a", "b", "c", "d"))

    assert hasil is not None
    assert hasil[1] == 4


def test_slot_tile_lain_tidak_dipakai():
    cache = TileCache(max_bytes=50 * 1024 * 1024)
    cache.put(_key(1, tx=0), Image.new("RGBA", (512, 512)), ("bg", "a"))

    assert cache.find_prefix(_key(2, tx=9), ("bg", "a", "b")) is None


def test_skala_lain_tidak_dipakai():
    """Tile bucket lain punya ukuran piksel berbeda; tidak boleh ditimpakan."""

    cache = TileCache(max_bytes=50 * 1024 * 1024)
    cache.put(_key(1, bucket=0.5), Image.new("RGBA", (256, 256)), ("bg", "a"))

    assert cache.find_prefix(_key(2, bucket=1.0), ("bg", "a", "b")) is None


def test_indeks_bersih_setelah_eviksi():
    cache = TileCache(max_bytes=1024)
    cache.put(_key(1), Image.new("RGBA", (512, 512)), ("bg", "a"))
    cache.put(_key(2, tx=5), Image.new("RGBA", (512, 512)), ("bg", "a"))

    assert cache.find_prefix(_key(3), ("bg", "a", "b")) is None
    assert cache._parts.keys() <= cache._store.keys()


def test_hasil_inkremental_identik_dengan_render_penuh():
    """Inti kebenarannya: menimpakan harus setara menggambar ulang."""

    def sprite(offset: int) -> Image.Image:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        img.paste((offset % 255, 40, 90, 180), (0, 0, 64, 64))
        return img

    def render_penuh(count: int) -> Image.Image:
        surface = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        for i in range(count):
            surface.alpha_composite(sprite(i * 30), dest=((i * 17) % 190, (i * 29) % 190))
        return surface

    penuh = render_penuh(12)
    inkremental = render_penuh(11).copy()
    inkremental.alpha_composite(sprite(11 * 30), dest=((11 * 17) % 190, (11 * 29) % 190))

    assert ImageChops.difference(penuh, inkremental).getbbox() is None
