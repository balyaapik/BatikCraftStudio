"""Sisipkan gambar (hasil BatikBrew / berkas luar) ke dokumen raster.

Karena unit pemisahan di model ini adalah LAYER, gambar yang disisipkan masuk
sebagai layer baru — sehingga tetap bisa dipindah atau dihapus sebagai satu
kesatuan, dan hasil batifikasi dari jendela studio bisa mendarat langsung di
dokumen tanpa melebur ke coretan yang sudah ada.

Gambar yang lebih besar dari kanvas diperkecil agar muat (rasio dijaga), lalu
diletakkan di tengah.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from batikcraft_studio.imaging.raster_document import RasterDocument
from batikcraft_studio.imaging.raster_layer import RasterLayer, RasterLayerError


def _decode_rgba(content: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            return image.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise RasterLayerError("Gambar tidak dapat dibaca.") from exc


def fit_within(
    image: Image.Image, max_width: int, max_height: int
) -> Image.Image:
    """Perkecil agar muat dalam kotak, jaga rasio. Tidak memperbesar."""

    if image.width <= max_width and image.height <= max_height:
        return image
    ratio = min(max_width / image.width, max_height / image.height)
    size = (max(1, round(image.width * ratio)), max(1, round(image.height * ratio)))
    return image.resize(size, Image.Resampling.LANCZOS)


def build_layer_from_image(
    content: bytes,
    canvas_width: int,
    canvas_height: int,
    *,
    name: str = "Gambar",
    position: tuple[int, int] | None = None,
) -> RasterLayer:
    """Buat layer seukuran kanvas berisi gambar yang disisipkan.

    ``position`` adalah titik kiri-atas dalam koordinat kanvas; None = tengah.
    """

    imported = fit_within(_decode_rgba(content), canvas_width, canvas_height)
    layer = RasterLayer(canvas_width, canvas_height, name=name)
    if position is None:
        left = (canvas_width - imported.width) // 2
        top = (canvas_height - imported.height) // 2
    else:
        left, top = position
    # Jepit agar sebagian gambar tetap terlihat walau posisi di luar kanvas.
    left = max(-imported.width + 1, min(left, canvas_width - 1))
    top = max(-imported.height + 1, min(top, canvas_height - 1))
    layer.composite(imported, (left, top))
    return layer


def insert_image_as_layer(
    document: RasterDocument,
    content: bytes,
    *,
    name: str = "Gambar",
    position: tuple[int, int] | None = None,
) -> RasterLayer:
    """Sisipkan gambar sebagai layer aktif baru di atas layer sekarang."""

    layer = build_layer_from_image(
        content, document.width, document.height, name=name, position=position
    )
    insert_at = document.active_index + 1
    document.layers.insert(insert_at, layer)
    document.active_index = insert_at
    return layer


def prepare_floating_image(
    content: bytes, canvas_width: int, canvas_height: int
) -> Image.Image:
    """Decode + perkecil agar muat; kembalikan gambar RGBA untuk diapungkan."""

    return fit_within(_decode_rgba(content), canvas_width, canvas_height)


def centered_position(
    image: Image.Image, canvas_width: int, canvas_height: int
) -> tuple[int, int]:
    return (
        (canvas_width - image.width) // 2,
        (canvas_height - image.height) // 2,
    )


def point_in_floating(
    px: float, py: float, image: Image.Image, position: tuple[int, int]
) -> bool:
    """Apakah titik proyek (px, py) berada di dalam gambar mengambang?"""

    left, top = position
    return left <= px < left + image.width and top <= py < top + image.height


def commit_floating_to_layer(
    layer: RasterLayer, image: Image.Image, position: tuple[int, int]
) -> tuple[int, int, int, int]:
    """Leburkan gambar mengambang ke bitmap layer. Kembalikan kotak terdampak."""

    left, top = position
    layer.composite(image, (left, top))
    return (left, top, left + image.width, top + image.height)


__all__ = [
    "build_layer_from_image",
    "centered_position",
    "commit_floating_to_layer",
    "fit_within",
    "insert_image_as_layer",
    "point_in_floating",
    "prepare_floating_image",
]
