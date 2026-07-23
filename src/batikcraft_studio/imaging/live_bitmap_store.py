"""Cache bitmap hidup bersama untuk layer canting raster kanvas utama.

Masalah: kanvas utama menyimpan bitmap layer sebagai PNG (bytes). Tiap goresan
meng-encode PNG penuh lalu renderer men-decode-nya lagi — dua operasi mahal
per goresan. Kanvas raster mandiri cepat karena menyimpan satu gambar PIL hidup.

Store ini menyimpan gambar PIL yang sudah didekode, dikunci ``asset_ref``, dan
DIBAGI antara sesi (yang mengecap goresan) dan renderer (yang menampilkan).
Dengan begitu:

* Sesi mengecap goresan ke gambar hidup (tanpa decode ulang base).
* Renderer memakai gambar hidup itu langsung (tanpa decode PNG).

Encode PNG tetap dilakukan untuk penyimpanan & undo, tapi decode ganda hilang.

Aman-thread: renderer berjalan di thread worker, sesi di thread utama.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

from PIL import Image

_LOCK = threading.RLock()
_STORE: "OrderedDict[str, Image.Image]" = OrderedDict()
_MAX_ENTRIES = 24


def put(asset_ref: str, image: Image.Image) -> None:
    """Simpan gambar hidup untuk ``asset_ref`` (RGBA)."""

    if not asset_ref:
        return
    with _LOCK:
        if asset_ref in _STORE:
            _STORE.move_to_end(asset_ref)
        _STORE[asset_ref] = image
        while len(_STORE) > _MAX_ENTRIES:
            _STORE.popitem(last=False)


def get(asset_ref: str | None) -> Image.Image | None:
    """Ambil gambar hidup, atau None bila tidak ada."""

    if not asset_ref:
        return None
    with _LOCK:
        image = _STORE.get(asset_ref)
        if image is not None:
            _STORE.move_to_end(asset_ref)
        return image


def discard(asset_ref: str | None) -> None:
    if not asset_ref:
        return
    with _LOCK:
        _STORE.pop(asset_ref, None)


def clear() -> None:
    with _LOCK:
        _STORE.clear()


__all__ = ["clear", "discard", "get", "put"]
