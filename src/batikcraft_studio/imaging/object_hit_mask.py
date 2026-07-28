"""Uji tumbukan berbasis tinta (alfa) untuk objek kanvas.

Mengapa modul ini ada
---------------------
``point_hits_affine_object`` hanya memeriksa KOTAK BATAS objek. Untuk sebagian
besar objek itu sudah cukup, tetapi tidak untuk **garis**: sebuah garis diagonal
dari sudut ke sudut memiliki kotak batas seluas seluruh kanvas sementara tintanya
hanya beberapa piksel. Akibatnya:

* garis "menelan" setiap klik di dalam kotak batasnya, sehingga objek di
  belakangnya tidak dapat dipilih; dan
* sebaliknya, ketika objek berkotak-batas besar lain berada di atasnya, garis
  itu sendiri tidak pernah terpilih -- penghapus jadi tidak bisa mengenainya.

Modul ini menambahkan pemeriksaan tahap kedua: setelah kotak batas cocok, alfa
objek pada titik tersebut diperiksa. Mask disimpan pada resolusi rendah (sisi
terpanjang ``_MASK_MAX_SIDE``) dan di-cache LRU, jadi biayanya tetap kecil.

Mask sengaja di-*dilate* satu piksel. Pada resolusi mask yang diperkecil sebuah
garis tipis dapat menghilang sama sekali; pelebaran ini menjaga garis tetap dapat
diklik dan membuat toleransi klik terasa wajar.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Mapping
from io import BytesIO
from typing import Any

from PIL import Image, ImageFilter, UnidentifiedImageError

from batikcraft_studio.domain import Layer, LayerKind, LayerObject, ObjectKind, Transform

from .affine_object import inverse_transform_point
from .shape import ShapeError, render_shape_image

#: Sisi terpanjang mask uji-tumbukan. 192 px cukup untuk membedakan tinta dari
#: ruang kosong tanpa membuat dekode gambar besar terasa di jalur klik.
_MASK_MAX_SIDE = 192
#: Nilai alfa minimum yang dianggap "ada tintanya".
_ALPHA_THRESHOLD = 8
#: Jumlah mask yang disimpan. Setiap entri paling besar 192*192 = 36 KB.
_CACHE_LIMIT = 96

_cache: OrderedDict[tuple[Any, ...], Image.Image | None] = OrderedDict()


def clear_hit_mask_cache() -> None:
    """Kosongkan cache mask. Dipakai oleh pengujian."""

    _cache.clear()


def precise_point_hits_object(
    item: LayerObject,
    assets: Mapping[str, bytes],
    x: float,
    y: float,
) -> bool:
    """True bila (*x*, *y*) mengenai piksel objek yang benar-benar terlihat.

    Kotak batas diperiksa lebih dulu karena jauh lebih murah. Bila mask tidak
    dapat dibangun (aset hilang, shape rusak), fungsi ini kembali ke perilaku
    kotak batas supaya tidak ada objek yang mendadak tak bisa dipilih.
    """

    local = inverse_transform_point(item, float(x), float(y))
    if local is None:
        return False
    half_width = item.bounds.width / 2
    half_height = item.bounds.height / 2
    if abs(local[0]) > half_width or abs(local[1]) > half_height:
        return False
    if item.opacity <= 0.0 or not item.visible:
        return False

    mask = _hit_mask(item, assets)
    if mask is None:
        return True

    u = (local[0] / item.bounds.width) + 0.5
    v = (local[1] / item.bounds.height) + 0.5
    column = min(mask.width - 1, max(0, int(u * mask.width)))
    row = min(mask.height - 1, max(0, int(v * mask.height)))
    return mask.getpixel((column, row)) >= _ALPHA_THRESHOLD


def _hit_mask(item: LayerObject, assets: Mapping[str, bytes]) -> Image.Image | None:
    key = _mask_key(item, assets)
    cached = _cache.get(key)
    if key in _cache:
        _cache.move_to_end(key)
        return cached
    mask = _build_mask(item, assets)
    _cache[key] = mask
    while len(_cache) > _CACHE_LIMIT:
        _cache.popitem(last=False)
    return mask


def _mask_key(item: LayerObject, assets: Mapping[str, bytes]) -> tuple[Any, ...]:
    if item.kind is ObjectKind.SHAPE:
        digest = hashlib.sha1(
            repr(sorted((str(k), repr(v)) for k, v in item.properties.items())).encode()
        ).hexdigest()[:16]
    else:
        content = assets.get(item.asset_ref) if item.asset_ref else None
        digest = hashlib.sha1(content).hexdigest()[:16] if content else ""
    return (item.object_id, item.kind, item.asset_ref, digest, item.bounds.width, item.bounds.height)


def _mask_size(item: LayerObject) -> tuple[int, int]:
    width = max(1.0, float(item.bounds.width))
    height = max(1.0, float(item.bounds.height))
    ratio = min(1.0, _MASK_MAX_SIDE / max(width, height))
    return max(1, round(width * ratio)), max(1, round(height * ratio))


def _build_mask(item: LayerObject, assets: Mapping[str, bytes]) -> Image.Image | None:
    width, height = _mask_size(item)
    try:
        if item.kind is ObjectKind.SHAPE:
            legacy = Layer(
                name=item.name,
                kind=LayerKind.SHAPE,
                transform=Transform(),
                properties={
                    **dict(item.properties),
                    "pixel_width": item.bounds.width,
                    "pixel_height": item.bounds.height,
                },
            )
            image = render_shape_image(legacy, width, height)
        else:
            if item.asset_ref is None:
                return None
            content = assets.get(item.asset_ref)
            if content is None:
                return None
            with Image.open(BytesIO(content)) as source:
                source.draft("RGBA", (width, height))
                source.load()
                image = source.convert("RGBA").resize(
                    (width, height), Image.Resampling.BILINEAR
                )
    except (ShapeError, UnidentifiedImageError, OSError, ValueError):
        return None
    alpha = image.getchannel("A")
    # MaxFilter melebarkan tinta satu piksel mask ke segala arah.
    return alpha.filter(ImageFilter.MaxFilter(3))


__all__ = ["clear_hit_mask_cache", "precise_point_hits_object"]
