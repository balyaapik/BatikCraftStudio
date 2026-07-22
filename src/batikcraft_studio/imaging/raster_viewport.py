"""Renderer viewport untuk dokumen raster.

Inilah sumber keringanan gaya MS Paint: menampilkan kanvas = memotong wilayah
yang terlihat dari bitmap layer lalu menskalakannya. TIDAK ada loop objek, tidak
ada komposit per-objek. Biayanya sebanding dengan luas LAYAR, bukan dengan isi
gambar — sehingga tetap sama ringannya entah kanvas berisi 5 atau 50.000 coretan.

Perataan latar (semua layer di bawah yang aktif) di-cache; saat menggambar,
hanya layer aktif yang berubah, jadi latar tidak perlu diratakan ulang.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageColor, ImageEnhance

from batikcraft_studio.imaging.raster_document import RasterDocument


@dataclass
class ViewportRequest:
    """Wilayah proyek yang terlihat dan skala tampilnya."""

    proj_left: float
    proj_top: float
    view_width: int
    view_height: int
    zoom: float


class RasterViewportRenderer:
    """Render dokumen raster untuk ditampilkan, dengan cache latar."""

    def __init__(self) -> None:
        self._below_cache: Image.Image | None = None
        self._below_signature: tuple[object, ...] | None = None
        self._above_cache: Image.Image | None = None
        self._above_signature: tuple[object, ...] | None = None

    def invalidate(self) -> None:
        self._below_cache = None
        self._below_signature = None
        self._above_cache = None
        self._above_signature = None

    # ------------------------------------------------------------------
    # Perataan berlapis dengan cache
    # ------------------------------------------------------------------

    @staticmethod
    def _layer_signature(layer: object) -> tuple[object, ...]:
        return (
            getattr(layer, "layer_id", None),
            getattr(layer, "visible", None),
            getattr(layer, "opacity", None),
            id(getattr(layer, "image", None)),
        )

    def _composite_range(
        self, document: RasterDocument, layers: list, base_rgba: Image.Image
    ) -> Image.Image:
        surface = base_rgba
        for layer in layers:
            if not layer.visible or layer.opacity <= 0:
                continue
            image = layer.image
            if layer.opacity < 1.0:
                alpha = image.getchannel("A")
                image = image.copy()
                image.putalpha(ImageEnhance.Brightness(alpha).enhance(layer.opacity))
            surface.alpha_composite(image)
        return surface

    def _below(self, document: RasterDocument) -> Image.Image:
        """Latar: semua layer di bawah yang aktif, di atas warna latar."""

        below = document.layers[: document.active_index]
        signature = (
            document.width,
            document.height,
            document.background_color,
            tuple(self._layer_signature(item) for item in below),
        )
        if self._below_signature == signature and self._below_cache is not None:
            return self._below_cache
        base = Image.new(
            "RGBA",
            (document.width, document.height),
            (*ImageColor.getrgb(document.background_color), 255),
        )
        result = self._composite_range(document, below, base)
        self._below_cache = result
        self._below_signature = signature
        return result

    def _above(self, document: RasterDocument) -> Image.Image | None:
        """Layer di atas yang aktif; None kalau tidak ada."""

        above = document.layers[document.active_index + 1 :]
        if not above:
            return None
        signature = (
            document.width,
            document.height,
            tuple(self._layer_signature(item) for item in above),
        )
        if self._above_signature == signature and self._above_cache is not None:
            return self._above_cache
        base = Image.new("RGBA", (document.width, document.height), (0, 0, 0, 0))
        result = self._composite_range(document, above, base)
        self._above_cache = result
        self._above_signature = signature
        return result

    def compose_full(self, document: RasterDocument) -> Image.Image:
        """Gambar penuh: latar + layer aktif + layer atas. RGBA."""

        surface = self._below(document).copy()
        active = document.active_layer
        if active.visible and active.opacity > 0:
            image = active.image
            if active.opacity < 1.0:
                alpha = image.getchannel("A")
                image = image.copy()
                image.putalpha(ImageEnhance.Brightness(alpha).enhance(active.opacity))
            surface.alpha_composite(image)
        above = self._above(document)
        if above is not None:
            surface.alpha_composite(above)
        return surface

    # ------------------------------------------------------------------
    # Render viewport
    # ------------------------------------------------------------------

    def compose_region(
        self, document: RasterDocument, box: tuple[int, int, int, int]
    ) -> Image.Image:
        """Komposit HANYA kotak ``box`` (kiri, atas, kanan, bawah).

        Ini yang membuat render benar-benar O(viewport): setiap layer dipotong
        ke kotak terlihat lebih dulu, jadi tidak ada gambar seukuran dokumen
        yang disalin. Latar (layer di bawah aktif) tetap di-cache utuh, tetapi
        yang diambil hanya potongannya.
        """

        left, top, right, bottom = box
        base_below = self._below(document).crop(box)
        surface = base_below
        active = document.active_layer
        if active.visible and active.opacity > 0:
            patch = active.image.crop(box)
            if active.opacity < 1.0:
                alpha = patch.getchannel("A")
                patch = patch.copy()
                patch.putalpha(ImageEnhance.Brightness(alpha).enhance(active.opacity))
            surface.alpha_composite(patch)
        above = self._above(document)
        if above is not None:
            surface.alpha_composite(above.crop(box))
        return surface

    def render(self, document: RasterDocument, request: ViewportRequest) -> Image.Image:
        """Potong wilayah terlihat lalu skalakan — inti keringanannya.

        Biaya = luas viewport, bukan luas dokumen atau jumlah coretan.
        """

        zoom = max(request.zoom, 1e-6)

        # Wilayah proyek yang terlihat (dijepit ke batas dokumen).
        left = max(0, int(request.proj_left))
        top = max(0, int(request.proj_top))
        right = min(document.width, int(request.proj_left + request.view_width / zoom) + 1)
        bottom = min(document.height, int(request.proj_top + request.view_height / zoom) + 1)
        if right <= left or bottom <= top:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

        patch = self.compose_region(document, (left, top, right, bottom))
        # Keluaran tidak boleh melebihi viewport; juga tidak boleh melebihi
        # dokumen yang terlihat setelah diskalakan.
        target_w = min(request.view_width, max(1, round((right - left) * zoom)))
        target_h = min(request.view_height, max(1, round((bottom - top) * zoom)))
        if (target_w, target_h) == patch.size:
            return patch
        resample = (
            Image.Resampling.NEAREST if zoom >= 1.0 else Image.Resampling.BILINEAR
        )
        return patch.resize((target_w, target_h), resample)


__all__ = ["RasterViewportRenderer", "ViewportRequest"]
