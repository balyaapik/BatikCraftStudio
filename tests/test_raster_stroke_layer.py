"""Komposit goresan ke satu bitmap layer canting (optimasi aplikasi utama)."""

from __future__ import annotations

import io

from PIL import Image

from batikcraft_studio.imaging.raster_stroke_layer import (
    blank_canvas_png,
    composite_stroke_onto_canvas,
)


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _open(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def test_kanvas_kosong_transparan():
    canvas = _open(blank_canvas_png(100, 80))
    assert canvas.size == (100, 80)
    assert canvas.getpixel((0, 0)) == (0, 0, 0, 0)


def test_kuas_meninggalkan_tanda():
    base = blank_canvas_png(100, 100)
    stroke = _png(Image.new("RGBA", (20, 20), (255, 0, 0, 255)))

    out = _open(composite_stroke_onto_canvas(base, stroke, 30, 30))

    assert out.getpixel((35, 35)) == (255, 0, 0, 255)
    assert out.getpixel((5, 5)) == (0, 0, 0, 0)


def test_goresan_akumulatif_tidak_saling_menghapus():
    base = blank_canvas_png(100, 100)
    s1 = _png(Image.new("RGBA", (20, 20), (255, 0, 0, 255)))
    s2 = _png(Image.new("RGBA", (20, 20), (0, 0, 255, 255)))

    step1 = composite_stroke_onto_canvas(base, s1, 30, 30)
    step2 = _open(composite_stroke_onto_canvas(step1, s2, 60, 60))

    assert step2.getpixel((35, 35)) == (255, 0, 0, 255)
    assert step2.getpixel((65, 65)) == (0, 0, 255, 255)


def test_penghapus_mengurangi_alfa():
    filled = _png(Image.new("RGBA", (100, 100), (0, 200, 0, 255)))
    mask = _png(Image.new("RGBA", (30, 30), (255, 255, 255, 255)))

    out = _open(composite_stroke_onto_canvas(filled, mask, 10, 10, erase=True))

    assert out.getpixel((20, 20))[3] == 0
    assert out.getpixel((80, 80))[3] == 255


def test_seratus_goresan_tetap_satu_bitmap():
    """Inti optimasi: N goresan = 1 aset, bukan N objek."""

    canvas = blank_canvas_png(400, 400)
    stroke = _png(Image.new("RGBA", (10, 10), (20, 20, 20, 255)))
    for i in range(100):
        canvas = composite_stroke_onto_canvas(canvas, stroke, i * 3, i * 3)

    result = _open(canvas)
    assert result.size == (400, 400)
    # Hasil tetap satu gambar; ukuran byte tetap wajar (bukan 100 objek terpisah).
    assert len(canvas) < 400 * 400 * 4


def test_penempatan_full_canvas_benar():
    """Regresi 0.9.7->0.9.8: goresan harus muncul di posisi yang digambar.

    Layer canting raster full-canvas berpusat di transform=(W/2, H/2) dan
    memerlukan pixel_width/pixel_height. Tanpa itu render gagal diam-diam
    (tidak ada yang muncul).
    """

    cw, ch = 200, 200
    base = blank_canvas_png(cw, ch)
    stroke = _png(Image.new("RGBA", (20, 20), (255, 0, 0, 255)))
    bitmap = _open(composite_stroke_onto_canvas(base, stroke, 30, 30))

    # Tiru penempatan renderer: bitmap berpusat di (cw/2, ch/2), zoom 1.
    tx, ty = cw / 2, ch / 2
    dest = (round(tx - bitmap.width / 2), round(ty - bitmap.height / 2))
    assert dest == (0, 0)

    surface = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    surface.alpha_composite(bitmap, dest=dest)
    assert surface.getpixel((35, 35)) == (255, 0, 0, 255)
    assert surface.getpixel((5, 5)) == (0, 0, 0, 0)


def test_composite_image_identik_dengan_bytes():
    """Jalur gambar-hidup harus menghasilkan piksel sama dengan jalur bytes."""

    from PIL import ImageChops

    from batikcraft_studio.imaging.raster_stroke_layer import (
        composite_stroke_onto_image,
    )

    base = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    stroke = _png(Image.new("RGBA", (30, 30), (255, 0, 0, 255)))

    via_image = composite_stroke_onto_image(base, stroke, 40, 40)
    via_bytes = _open(composite_stroke_onto_canvas(_png(base), stroke, 40, 40))

    assert ImageChops.difference(via_image, via_bytes).getbbox() is None


def test_composite_image_tidak_mengubah_base():
    """Base harus utuh (undo menyimpan state 'sebelum')."""

    from batikcraft_studio.imaging.raster_stroke_layer import (
        composite_stroke_onto_image,
    )

    base = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    composite_stroke_onto_image(base, _png(Image.new("RGBA", (20, 20), (1, 2, 3, 255))), 10, 10)

    assert base.getpixel((15, 15)) == (0, 0, 0, 0)
