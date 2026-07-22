"""Model layer raster — inti perombakan kanvas gaya MS Paint.

Setiap layer adalah satu bitmap RGBA. Menggambar berarti menulis piksel ke
bitmap itu; objek tidak lagi ada, jadi biaya menggambar sebanding dengan luas
kuas, bukan dengan isi kanvas. Yang tetap terpisah dan bisa dipindah/dihapus
sendiri adalah LAYER-nya.

Ukuran kanvas bisa diubah kapan saja. Aturan resize di sini adalah gaya
"Resize Canvas" (bukan "Resize Image"): piksel yang sudah ada dipertahankan apa
adanya — memperbesar menambah ruang transparan di kanan/bawah, memperkecil
memotong tepinya. Dengan begitu karya yang sudah digambar tidak pernah menjadi
buram akibat perubahan ukuran.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from io import BytesIO
from typing import Iterable
from uuid import uuid4

from PIL import Image

#: Batas atas sisi kanvas (A3 300dpi ~4961x7016 masih di bawah ini).
MAX_RASTER_DIMENSION = 8192


class RasterLayerError(RuntimeError):
    """Kesalahan operasi pada layer raster."""


def _blank(width: int, height: int) -> Image.Image:
    return Image.new("RGBA", (width, height), (0, 0, 0, 0))


@dataclass
class RasterLayer:
    """Satu layer bitmap RGBA yang bisa digambari."""

    width: int
    height: int
    name: str = "Layer"
    layer_id: str = field(default_factory=lambda: str(uuid4()))
    visible: bool = True
    opacity: float = 1.0
    _image: Image.Image | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.width = _validate_dimension(self.width, "lebar")
        self.height = _validate_dimension(self.height, "tinggi")
        self.opacity = _validate_opacity(self.opacity)
        if self._image is None:
            self._image = _blank(self.width, self.height)
        elif self._image.size != (self.width, self.height):
            raise RasterLayerError(
                "Ukuran bitmap tidak cocok dengan dimensi layer."
            )
        if self._image.mode != "RGBA":
            self._image = self._image.convert("RGBA")

    # ------------------------------------------------------------------
    # Akses bitmap
    # ------------------------------------------------------------------

    @property
    def image(self) -> Image.Image:
        """Bitmap layer. JANGAN dimodifikasi langsung tanpa lewat API ini."""

        assert self._image is not None  # dijamin __post_init__
        return self._image

    def composite(self, patch: Image.Image, box: tuple[int, int]) -> None:
        """Timpakan ``patch`` (RGBA) ke posisi ``box`` — inilah 'menggambar'.

        Biayanya sebesar ``patch``, bukan sebesar layer. Inilah yang membuat
        menggambar tetap ringan pada kanvas seramai apa pun.
        """

        if patch.mode != "RGBA":
            patch = patch.convert("RGBA")
        self.image.alpha_composite(patch, dest=box)

    def erase(self, patch_alpha: Image.Image, box: tuple[int, int]) -> None:
        """Kurangi alfa layer memakai alfa ``patch_alpha`` (mode L) — penghapus."""

        x, y = box
        region = self.image.crop((x, y, x + patch_alpha.width, y + patch_alpha.height))
        r, g, b, a = region.split()
        from PIL import ImageChops

        keep = ImageChops.subtract(a, patch_alpha)
        region = Image.merge("RGBA", (r, g, b, keep))
        self.image.paste(region, (x, y))

    def clear(self) -> None:
        self._image = _blank(self.width, self.height)

    # ------------------------------------------------------------------
    # Resize kanvas (pertahankan piksel; tambah/potong ruang)
    # ------------------------------------------------------------------

    def resized_canvas(
        self, width: int, height: int, *, anchor: str = "nw"
    ) -> "RasterLayer":
        """Kembalikan layer dengan kanvas berukuran baru, piksel dipertahankan.

        Ini gaya "Resize Canvas": isi lama tidak diregangkan. Memperbesar
        menambah ruang transparan; memperkecil memotong. ``anchor`` menentukan
        di mana isi lama diletakkan pada kanvas baru.
        """

        width = _validate_dimension(width, "lebar")
        height = _validate_dimension(height, "tinggi")
        canvas = _blank(width, height)
        offset_x, offset_y = _anchor_offset(
            anchor, self.width, self.height, width, height
        )
        canvas.alpha_composite(self.image, dest=(offset_x, offset_y))
        return RasterLayer(
            width=width,
            height=height,
            name=self.name,
            layer_id=self.layer_id,
            visible=self.visible,
            opacity=self.opacity,
            _image=canvas,
        )

    # ------------------------------------------------------------------
    # Serialisasi
    # ------------------------------------------------------------------

    def to_png_bytes(self) -> bytes:
        buffer = BytesIO()
        self.image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    @classmethod
    def from_png_bytes(
        cls,
        content: bytes,
        *,
        name: str = "Layer",
        layer_id: str | None = None,
        visible: bool = True,
        opacity: float = 1.0,
    ) -> "RasterLayer":
        with Image.open(BytesIO(content)) as image:
            image.load()
            rgba = image.convert("RGBA")
        return cls(
            width=rgba.width,
            height=rgba.height,
            name=name,
            layer_id=layer_id or str(uuid4()),
            visible=visible,
            opacity=opacity,
            _image=rgba,
        )

    def with_meta(
        self,
        *,
        name: str | None = None,
        visible: bool | None = None,
        opacity: float | None = None,
    ) -> "RasterLayer":
        return replace(
            self,
            name=self.name if name is None else name,
            visible=self.visible if visible is None else visible,
            opacity=self.opacity if opacity is None else opacity,
            _image=self._image,
        )


def _validate_dimension(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RasterLayerError(f"{label} kanvas harus bilangan bulat.")
    if not 1 <= value <= MAX_RASTER_DIMENSION:
        raise RasterLayerError(
            f"{label} kanvas harus antara 1 dan {MAX_RASTER_DIMENSION}."
        )
    return value


def _validate_opacity(value: float) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise RasterLayerError("Opasitas layer harus antara 0 dan 1.")
    return number


def _anchor_offset(
    anchor: str, old_w: int, old_h: int, new_w: int, new_h: int
) -> tuple[int, int]:
    """Titik kiri-atas untuk meletakkan isi lama pada kanvas baru."""

    anchor = anchor.lower()
    if anchor in {"nw", "topleft", "top-left"}:
        return 0, 0
    dx = new_w - old_w
    dy = new_h - old_h
    horizontal = {"w": 0, "e": dx}.get(anchor[-1:], dx // 2)
    vertical = {"n": 0, "s": dy}.get(anchor[:1], dy // 2)
    if anchor == "center":
        return dx // 2, dy // 2
    # Kombinasi seperti "ne", "sw" ditangani per-sumbu.
    x = 0 if "w" in anchor else dx if "e" in anchor else dx // 2
    y = 0 if "n" in anchor else dy if "s" in anchor else dy // 2
    return x, y


def flatten_layers(
    layers: Iterable[RasterLayer],
    width: int,
    height: int,
    background_color: str = "#FFFFFF",
) -> Image.Image:
    """Gabungkan layer terlihat jadi satu gambar RGB — dasar pustaka & cetak.

    Pustaka berasal dari dokumen PENUH ini, bukan dari objek per objek.
    """

    from PIL import ImageColor

    base = Image.new("RGBA", (width, height), (*ImageColor.getrgb(background_color), 255))
    for layer in layers:
        if not layer.visible or layer.opacity <= 0:
            continue
        surface = layer.image
        if surface.size != (width, height):
            fitted = _blank(width, height)
            fitted.alpha_composite(surface, dest=(0, 0))
            surface = fitted
        if layer.opacity < 1.0:
            from PIL import ImageEnhance

            alpha = surface.getchannel("A")
            surface = surface.copy()
            surface.putalpha(ImageEnhance.Brightness(alpha).enhance(layer.opacity))
        base.alpha_composite(surface)
    return base.convert("RGB")


__all__ = [
    "MAX_RASTER_DIMENSION",
    "RasterLayer",
    "RasterLayerError",
    "flatten_layers",
]
