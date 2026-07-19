"""Regresi untuk fill scanline dan morfologi teriterasi."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter

from batikcraft_studio.application.hotfix_session import (
    _interior_from_free_space,
    _iterated_morphology,
)


def _ring_free_space(size: int = 96) -> Image.Image:
    barrier = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(barrier)
    draw.ellipse((8, 8, size - 8, size - 8), outline=255, width=6)
    return barrier.point(lambda value: 0 if value else 255)


def test_iterated_morphology_matches_single_large_rank_filter() -> None:
    image = _ring_free_space()
    for radius in (1, 2, 4):
        fast = _iterated_morphology(image, radius, ImageFilter.MaxFilter)
        slow = image.filter(ImageFilter.MaxFilter(radius * 2 + 1))
        assert fast.tobytes() == slow.tobytes()


def test_interior_from_free_space_marks_only_enclosed_area() -> None:
    free = _ring_free_space()
    interior = _interior_from_free_space(free)
    center = interior.size[0] // 2
    assert interior.getpixel((center, center)) == 255  # dalam ring
    assert interior.getpixel((0, 0)) == 0  # eksterior
    assert interior.getpixel((10, center)) == 0  # piksel garis/barier


def test_interior_empty_when_not_closed() -> None:
    free = Image.new("L", (64, 64), 255)  # tidak ada garis sama sekali
    interior = _interior_from_free_space(free)
    assert interior.getbbox() is None
