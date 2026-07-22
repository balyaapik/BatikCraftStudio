"""Undo/redo hemat memori untuk kanvas raster.

Menyimpan seluruh bitmap layer tiap langkah terlalu boros (A3 = ~133 MB per
snapshot). Sebagai gantinya, tiap suntingan hanya menyimpan WILAYAH yang
benar-benar berubah: kotak pembatas + piksel 'sebelum' dan 'sesudah' di kotak
itu. Sama seperti editor gambar sungguhan.

Alur: sebelum menggambar, simpan salinan bitmap layer aktif. Setelah selesai,
bandingkan untuk menemukan kotak yang berubah, lalu simpan hanya potongan itu.
Salinan penuh sementara hanya hidup selama satu goresan lalu dibuang.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageChops

_DEFAULT_MAX_BYTES = 256 * 1024 * 1024


@dataclass
class LayerRegionEdit:
    """Satu suntingan piksel pada wilayah persegi sebuah layer."""

    layer_id: str
    box: tuple[int, int, int, int]
    before: Image.Image
    after: Image.Image

    @property
    def nbytes(self) -> int:
        def size(image: Image.Image) -> int:
            return image.width * image.height * len(image.getbands())

        return size(self.before) + size(self.after)


def diff_region(before: Image.Image, after: Image.Image) -> tuple[int, int, int, int] | None:
    """Kotak pembatas piksel yang berbeda, atau None kalau identik."""

    return ImageChops.difference(before, after).getbbox()


class UndoStack:
    """Riwayat undo/redo berbasis wilayah, dengan batas memori."""

    def __init__(self, max_bytes: int = _DEFAULT_MAX_BYTES) -> None:
        self._max_bytes = max_bytes
        self._undo: list[LayerRegionEdit] = []
        self._redo: list[LayerRegionEdit] = []
        self._used = 0

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def push(self, edit: LayerRegionEdit) -> None:
        """Catat suntingan baru. Menghapus riwayat redo (percabangan baru)."""

        for stale in self._redo:
            self._used -= stale.nbytes
        self._redo.clear()
        self._undo.append(edit)
        self._used += edit.nbytes
        self._evict()

    def record_layer_change(
        self, layer_id: str, before: Image.Image, after: Image.Image
    ) -> bool:
        """Bandingkan sebelum/sesudah; simpan hanya wilayah berubah. True bila ada."""

        box = diff_region(before, after)
        if box is None:
            return False
        self.push(
            LayerRegionEdit(
                layer_id=layer_id,
                box=box,
                before=before.crop(box).copy(),
                after=after.crop(box).copy(),
            )
        )
        return True

    def undo(self, document: object) -> str | None:
        return self._apply(document, self._undo, self._redo, use_before=True)

    def redo(self, document: object) -> str | None:
        return self._apply(document, self._redo, self._undo, use_before=False)

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._used = 0

    # ------------------------------------------------------------------

    def _apply(
        self,
        document: object,
        source: list[LayerRegionEdit],
        target: list[LayerRegionEdit],
        *,
        use_before: bool,
    ) -> str | None:
        if not source:
            return None
        edit = source.pop()
        layer = _find_layer(document, edit.layer_id)
        if layer is None:
            # Layer sudah tidak ada; buang saja suntingannya.
            self._used -= edit.nbytes
            return None
        patch = edit.before if use_before else edit.after
        layer.image.paste(patch, (edit.box[0], edit.box[1]))
        target.append(edit)
        return edit.layer_id

    def _evict(self) -> None:
        # Buang suntingan TERTUA saat melewati batas memori.
        while self._used > self._max_bytes and len(self._undo) > 1:
            stale = self._undo.pop(0)
            self._used -= stale.nbytes


def _find_layer(document: object, layer_id: str) -> object | None:
    for layer in getattr(document, "layers", ()):
        if getattr(layer, "layer_id", None) == layer_id:
            return layer
    return None


__all__ = ["LayerRegionEdit", "UndoStack", "diff_region"]
