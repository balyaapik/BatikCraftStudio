"""Komposisi gambar preview untuk pustaka aset dan model.

Preview dipakai sebagai wajah listing di BatikCraftWeb, jadi harus estetis:
kolase rapi di atas latar kertas batik dengan bingkai tipis, bukan sekadar
gambar mentah pertama.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

_PAPER = (244, 233, 216, 255)
_FRAME = (122, 62, 42, 255)


def compose_collage_preview(
    images: list[bytes],
    *,
    size: int = 768,
    background: tuple[int, int, int, int] = _PAPER,
) -> bytes:
    """Susun hingga 9 gambar menjadi satu kolase preview persegi."""

    tiles: list[Image.Image] = []
    for content in images[:9]:
        try:
            with Image.open(BytesIO(content)) as source:
                source.load()
                tiles.append(source.convert("RGBA"))
        except Exception:  # noqa: BLE001 - lewati gambar rusak
            continue
    if not tiles:
        raise ValueError("Tidak ada gambar valid untuk preview.")

    columns = 1 if len(tiles) == 1 else 2 if len(tiles) <= 4 else 3
    rows = -(-len(tiles) // columns)
    gutter = max(8, size // 48)
    cell = (size - gutter * (columns + 1)) // columns
    height = gutter * (rows + 1) + cell * rows

    canvas = Image.new("RGBA", (size, height), background)
    draw = ImageDraw.Draw(canvas)
    for index, tile in enumerate(tiles):
        row, column = divmod(index, columns)
        left = gutter + column * (cell + gutter)
        top = gutter + row * (cell + gutter)
        fitted = tile.copy()
        fitted.thumbnail((cell, cell), Image.Resampling.LANCZOS)
        offset_x = left + (cell - fitted.width) // 2
        offset_y = top + (cell - fitted.height) // 2
        canvas.alpha_composite(fitted, (offset_x, offset_y))
        draw.rectangle(
            (left - 2, top - 2, left + cell + 2, top + cell + 2),
            outline=_FRAME,
            width=2,
        )
    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG")
    return output.getvalue()


def extract_model_pack_preview(path: str | Path) -> bytes | None:
    """Ambil gambar preview/sample pertama dari arsip ``.batikmodel``."""

    source = Path(path)
    if not source.is_file():
        return None
    try:
        with zipfile.ZipFile(source, "r") as archive:
            names = sorted(archive.namelist())
            preferred = [
                name
                for name in names
                if name.casefold().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
            preferred.sort(
                key=lambda name: (
                    0 if "preview" in name.casefold() else
                    1 if "sample" in name.casefold() else 2,
                    name,
                )
            )
            for name in preferred:
                content = archive.read(name)
                try:
                    with Image.open(BytesIO(content)) as image:
                        image.verify()
                    return content
                except Exception:  # noqa: BLE001
                    continue
    except (OSError, zipfile.BadZipFile):
        return None
    return None


__all__ = ["compose_collage_preview", "extract_model_pack_preview"]
