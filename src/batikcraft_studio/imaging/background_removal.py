"""Penghapusan background otomatis untuk foto objek sebelum batifikasi.

Foto berlatar (meja, dinding, studio) membuat SDXL ikut membatikkan latarnya,
sehingga hasilnya bukan ornamen tunggal. Modul ini memisahkan objek dari
latarnya lebih dulu: latar dijadikan transparan, objek dipertahankan utuh.

Pendekatannya sengaja deterministik dan tanpa dependensi berat: banjir warna
dari tepi gambar (latar hampir selalu menyentuh tepi), lalu tepian dihaluskan.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageFilter

# Toleransi selisih warna terhadap warna latar; makin besar makin agresif.
_DEFAULT_TOLERANCE = 32
# Bila alpha yang sudah ada menutup < ambang ini, gambar dianggap belum
# memiliki latar transparan.
_EXISTING_ALPHA_RATIO = 0.02


def has_transparent_background(image: Image.Image) -> bool:
    """True bila gambar sudah memiliki area transparan yang berarti."""

    if image.mode not in ("RGBA", "LA"):
        return False
    alpha = image.getchannel("A")
    histogram = alpha.histogram()
    transparent = sum(histogram[:16])
    total = image.width * image.height
    return total > 0 and transparent / total >= _EXISTING_ALPHA_RATIO


def _edge_background_color(image: Image.Image) -> tuple[int, int, int]:
    """Warna latar diperkirakan dari piksel tepi (modus kasar)."""

    rgb = image.convert("RGB")
    width, height = rgb.size
    samples: list[tuple[int, int, int]] = []
    step = max(1, min(width, height) // 64)
    for x in range(0, width, step):
        samples.append(rgb.getpixel((x, 0)))
        samples.append(rgb.getpixel((x, height - 1)))
    for y in range(0, height, step):
        samples.append(rgb.getpixel((0, y)))
        samples.append(rgb.getpixel((width - 1, y)))

    # Kuantisasi agar gradasi lembut tetap terkelompok.
    buckets: dict[tuple[int, int, int], int] = {}
    for red, green, blue in samples:
        key = (red // 16, green // 16, blue // 16)
        buckets[key] = buckets.get(key, 0) + 1
    dominant = max(buckets, key=buckets.get)
    matching = [
        sample
        for sample in samples
        if (sample[0] // 16, sample[1] // 16, sample[2] // 16) == dominant
    ]
    count = len(matching)
    return (
        sum(item[0] for item in matching) // count,
        sum(item[1] for item in matching) // count,
        sum(item[2] for item in matching) // count,
    )


def remove_background(
    content: bytes,
    *,
    tolerance: int = _DEFAULT_TOLERANCE,
    feather: int = 2,
) -> tuple[bytes, bool]:
    """Kembalikan (PNG RGBA, apakah latar dihapus).

    Bila gambar sudah transparan, isinya dikembalikan apa adanya sehingga
    aset yang sudah rapi tidak dirusak.
    """

    with Image.open(BytesIO(content)) as source:
        source.load()
        image = source.convert("RGBA")

    if has_transparent_background(image):
        return content, False

    background = _edge_background_color(image)
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()

    # Banjir dari seluruh piksel tepi: hanya latar yang tersambung ke tepi yang
    # dihapus, sehingga warna serupa di dalam objek tetap aman.
    visited = bytearray(width * height)
    stack: list[tuple[int, int]] = []
    for x in range(width):
        stack.append((x, 0))
        stack.append((x, height - 1))
    for y in range(height):
        stack.append((0, y))
        stack.append((width - 1, y))

    limit = int(tolerance) * 3
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        index = y * width + x
        if visited[index]:
            continue
        red, green, blue = pixels[x, y]
        distance = (
            abs(red - background[0])
            + abs(green - background[1])
            + abs(blue - background[2])
        )
        if distance > limit:
            continue
        visited[index] = 1
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    mask = Image.frombytes("L", (width, height), bytes(visited)).point(
        lambda value: 0 if value else 255
    )
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather))
        mask = mask.point(lambda value: 255 if value >= 128 else value)

    if mask.getbbox() is None:
        # Seluruh gambar terbaca sebagai latar: jangan hapus apa pun.
        return content, False

    cleaned = image.copy()
    cleaned.putalpha(mask)
    output = BytesIO()
    cleaned.save(output, format="PNG")
    return output.getvalue(), True


__all__ = ["has_transparent_background", "remove_background"]
