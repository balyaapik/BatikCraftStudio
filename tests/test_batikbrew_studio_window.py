"""Studio Batifikasi BatikBrew — logika yang tidak bergantung Tk.

Alur baru: gambar diseret ke jendela mandiri, bukan dipilih dari kanvas.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from batikcraft_studio.ui.batikbrew_studio_window import (
    build_thumbnail,
    is_supported_image,
    load_source_image,
    parse_dropped_paths,
)


def _png_bytes(size: tuple[int, int] = (400, 300)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (180, 90, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("C:/a.png", ["C:/a.png"]),
        ("{C:/ada spasi/a.png}", ["C:/ada spasi/a.png"]),
        ("{C:/ada spasi/a.png} C:/b.png", ["C:/ada spasi/a.png", "C:/b.png"]),
        ("C:/b.png {C:/x y/c.png}", ["C:/b.png", "C:/x y/c.png"]),
        ("{C:/a.png}", ["C:/a.png"]),
        ("{C:/satu dua/d.png} {C:/e f.png}", ["C:/satu dua/d.png", "C:/e f.png"]),
        ("", []),
    ],
)
def test_lintasan_drop_diuraikan_benar(payload, expected):
    """tkdnd membungkus lintasan berspasi dengan kurung kurawal."""

    hasil = [str(path).replace("\\", "/") for path in parse_dropped_paths(payload)]

    assert hasil == expected


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"])
def test_format_gambar_didukung(suffix):
    assert is_supported_image(Path(f"motif{suffix}"))


@pytest.mark.parametrize("suffix", [".txt", ".pdf", ".svg", ".batikcraft", ""])
def test_format_lain_ditolak(suffix):
    assert not is_supported_image(Path(f"motif{suffix}"))


def test_huruf_besar_kecil_tidak_masalah():
    assert is_supported_image(Path("MOTIF.PNG"))
    assert is_supported_image(Path("Motif.JpEg"))


def test_thumbnail_muat_dalam_kotak():
    thumbnail = build_thumbnail(_png_bytes((1024, 512)))

    assert thumbnail is not None
    assert thumbnail.width <= 128
    assert thumbnail.height <= 128


def test_thumbnail_menjaga_rasio_aspek():
    thumbnail = build_thumbnail(_png_bytes((800, 400)))

    assert thumbnail is not None
    assert thumbnail.width == pytest.approx(thumbnail.height * 2, rel=0.05)


def test_thumbnail_data_rusak_tidak_melempar():
    assert build_thumbnail(b"bukan gambar") is None


def test_memuat_gambar_sumber(tmp_path):
    berkas = tmp_path / "botol.png"
    berkas.write_bytes(_png_bytes())

    sumber = load_source_image(berkas)

    assert sumber.label == "botol.png"
    assert sumber.content == berkas.read_bytes()
    assert sumber.thumbnail is not None
    assert sumber.path == berkas
