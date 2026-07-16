"""Generate a deterministic Batik reference when the user selects one object only."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageStat, UnidentifiedImageError

from batikcraft_studio.imaging.structured_batification import BatificationError


def build_default_batik_reference(
    source_content: bytes,
    *,
    size: int = 256,
) -> bytes:
    """Return a classic soga/Kawung-inspired PNG used as an AI motif reference.

    The source image is decoded so corrupt input still fails before inference. A small
    amount of its average colour is mixed into the mori base, while the actual pattern
    stays recognisably Batik. The result is deterministic and contains no random state.
    """

    if isinstance(size, bool) or not isinstance(size, int) or not 64 <= size <= 1024:
        raise BatificationError("Ukuran referensi Batik otomatis harus 64 sampai 1024 px.")
    try:
        with Image.open(BytesIO(source_content)) as source:
            source.load()
            sample = source.convert("RGB").resize((32, 32), Image.Resampling.BILINEAR)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BatificationError("Objek sumber tidak memiliki gambar yang dapat dibaca.") from exc

    mean = tuple(round(value) for value in ImageStat.Stat(sample).mean[:3])
    mori = _mix((235, 219, 184), mean, 0.12)
    soga_dark = (67, 39, 27)
    soga = (126, 72, 41)
    wax = (213, 168, 96)
    mengkudu = (128, 40, 48)

    image = Image.new("RGBA", (size, size), (*mori, 255))
    draw = ImageDraw.Draw(image)
    step = max(32, size // 4)
    radius = max(14, step // 3)
    line_width = max(2, size // 128)

    for offset in range(-size, size * 2, step):
        draw.line(
            (offset, -step, offset + size + step, size + step),
            fill=(*wax, 255),
            width=line_width,
        )
        draw.line(
            (offset, size + step, offset + size + step, -step),
            fill=(*wax, 255),
            width=line_width,
        )

    for row, y in enumerate(range(0, size + step, step)):
        shift = step // 2 if row % 2 else 0
        for x in range(-step + shift, size + step, step):
            box = (x - radius, y - radius, x + radius, y + radius)
            draw.ellipse(box, outline=(*soga_dark, 255), width=line_width + 1)
            inner = radius // 2
            draw.ellipse(
                (x - inner, y - inner, x + inner, y + inner),
                outline=(*soga, 255),
                width=line_width,
            )
            draw.line(
                (x - radius, y, x + radius, y),
                fill=(*soga, 255),
                width=line_width,
            )
            draw.line(
                (x, y - radius, x, y + radius),
                fill=(*soga, 255),
                width=line_width,
            )
            dot = max(2, radius // 7)
            draw.ellipse(
                (x - dot, y - dot, x + dot, y + dot),
                fill=(*mengkudu, 255),
            )

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _mix(left: tuple[int, int, int], right: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(
        max(0, min(255, round(a * (1.0 - amount) + b * amount)))
        for a, b in zip(left, right, strict=True)
    )


__all__ = ["build_default_batik_reference"]
