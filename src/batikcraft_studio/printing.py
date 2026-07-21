"""Cetak proyek: kirim ke printer sistem atau simpan sebagai berkas cetak.

Render memakai penampil proyek yang sama dengan ekspor, lalu:

* **Cetak** — menyerahkan berkas ke printer bawaan sistem operasi.
* **Cetak Sebagai** — menulis PDF/PNG pada lokasi pilihan pengguna.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping

from PIL import Image

from batikcraft_studio.imaging.renderer import render_project_preview

# 300 dpi pada sisi terpanjang, dibatasi agar tidak meledak untuk kanvas besar.
_MAX_PRINT_PIXELS = 6000
_A4_POINTS = (595, 842)


class PrintError(RuntimeError):
    """Kegagalan menyiapkan atau mengirim hasil cetak."""


def render_for_print(project: object, assets: Mapping[str, bytes]) -> Image.Image:
    """Render proyek pada resolusi cetak dengan latar putih (bukan transparan)."""

    canvas = project.canvas  # type: ignore[attr-defined]
    scale = min(
        _MAX_PRINT_PIXELS / max(canvas.width, canvas.height),
        4.0,
    )
    scale = max(1.0, scale)
    width = max(1, round(canvas.width * scale))
    height = max(1, round(canvas.height * scale))
    try:
        rendered = render_project_preview(
            project, assets, max_width=width, max_height=height
        )
    except Exception as exc:  # noqa: BLE001 - ubah menjadi galat cetak yang jelas
        raise PrintError(f"Proyek tidak dapat dirender untuk dicetak: {exc}") from exc

    image = rendered.image if hasattr(rendered, "image") else rendered
    flattened = Image.new("RGB", image.size, "white")
    flattened.paste(image, mask=image.getchannel("A") if image.mode == "RGBA" else None)
    return flattened


def save_print_file(
    project: object,
    assets: Mapping[str, bytes],
    destination: str | Path,
    *,
    fit_page: bool = True,
) -> Path:
    """Tulis berkas cetak (.pdf atau gambar) ke *destination*."""

    path = Path(destination).expanduser()
    image = render_for_print(project, assets)
    suffix = path.suffix.casefold()
    try:
        if suffix == ".pdf":
            page = _fit_to_page(image) if fit_page else image
            page.save(path, format="PDF", resolution=300.0)
        elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            image.save(path)
        else:
            path = path.with_suffix(".pdf")
            page = _fit_to_page(image) if fit_page else image
            page.save(path, format="PDF", resolution=300.0)
    except OSError as exc:
        raise PrintError(f"Berkas cetak tidak dapat ditulis: {exc}") from exc
    return path


def _fit_to_page(image: Image.Image) -> Image.Image:
    """Tempatkan gambar di tengah halaman A4 potret/lanskap sesuai orientasinya."""

    page_width, page_height = _A4_POINTS
    if image.width > image.height:
        page_width, page_height = page_height, page_width
    # Skala halaman ke 300 dpi agar hasil cetak tajam.
    scale = 300 / 72
    page_size = (round(page_width * scale), round(page_height * scale))
    fitted = image.copy()
    fitted.thumbnail(page_size, Image.LANCZOS)
    page = Image.new("RGB", page_size, "white")
    page.paste(
        fitted,
        ((page_size[0] - fitted.width) // 2, (page_size[1] - fitted.height) // 2),
    )
    return page


def send_to_printer(project: object, assets: Mapping[str, bytes]) -> Path:
    """Cetak proyek memakai printer bawaan sistem; kembalikan berkas sementara."""

    temporary = Path(tempfile.gettempdir()) / "batikcraft-cetak.pdf"
    save_print_file(project, assets, temporary)
    try:
        if os.name == "nt":
            # Verb 'print' membuka printer default tanpa jendela tambahan.
            os.startfile(str(temporary), "print")  # type: ignore[attr-defined]  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["lp", str(temporary)], check=True)  # noqa: S603,S607
        else:
            subprocess.run(["lp", str(temporary)], check=True)  # noqa: S603,S607
    except FileNotFoundError as exc:
        raise PrintError(
            "Perintah cetak sistem tidak ditemukan. Gunakan 'Cetak Sebagai…' "
            f"lalu cetak berkasnya secara manual. Detail: {exc}"
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise PrintError(
            "Printer sistem tidak dapat dihubungi. Gunakan 'Cetak Sebagai…' "
            f"lalu cetak berkasnya secara manual. Detail: {exc}"
        ) from exc
    return temporary


__all__ = ["PrintError", "render_for_print", "save_print_file", "send_to_printer"]
