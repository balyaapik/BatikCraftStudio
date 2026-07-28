"""Optimisasi kanvas untuk garis berukuran besar dan penghapusnya."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from batikcraft_studio.application import DestructiveEraserProjectSession
from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerObject,
    ObjectKind,
    Transform,
)
from batikcraft_studio.domain.models import ObjectBounds
from batikcraft_studio.imaging.object_hit_mask import (
    clear_hit_mask_cache,
    precise_point_hits_object,
)
from batikcraft_studio.imaging.shape import (
    _MAX_BAND_PIXELS,
    _SUPERSAMPLE_2_MAX_AREA,
    _SUPERSAMPLE_4_MAX_AREA,
    _draw_shape,
    _supersample_factor,
    build_shape_geometry,
    parse_shape_properties,
    render_shape_image,
)


def _line_layer(width: float, height: float, stroke_width: float = 6.0) -> tuple[Layer, int, int]:
    geometry = build_shape_geometry(
        "line", (0.0, 0.0), (width, height), stroke_width=stroke_width
    )
    layer = Layer(
        name="Garis",
        kind=LayerKind.SHAPE,
        transform=Transform(),
        properties=geometry.properties,
    )
    return (
        layer,
        int(geometry.properties["pixel_width"]),
        int(geometry.properties["pixel_height"]),
    )


def _line_object(width: float, height: float, stroke_width: float = 6.0) -> LayerObject:
    geometry = build_shape_geometry(
        "line", (0.0, 0.0), (width, height), stroke_width=stroke_width
    )
    return LayerObject(
        name="Garis",
        kind=ObjectKind.SHAPE,
        transform=Transform(x=geometry.center_x, y=geometry.center_y),
        bounds=ObjectBounds(
            geometry.properties["pixel_width"], geometry.properties["pixel_height"]
        ),
        properties=geometry.properties,
    )


# ---------------------------------------------------------------------------
# Rasterisasi shape
# ---------------------------------------------------------------------------


def test_supersample_factor_follows_an_area_budget_not_the_longest_side() -> None:
    assert _supersample_factor(512, 512) == 4
    assert _supersample_factor(2048, 2048) == 4
    # Aturan lama memberi 2x pada bentuk pipih ini walau luasnya sangat kecil.
    assert _supersample_factor(4096, 64) == 4
    assert _supersample_factor(3000, 3000) == 2
    assert _supersample_factor(6010, 4510) == 2
    assert _supersample_factor(9000, 7000) == 1


def test_supersample_budget_bounds_the_intermediate_buffer() -> None:
    for width, height in ((512, 512), (2048, 2048), (4096, 64), (3000, 3000), (9000, 7000)):
        factor = _supersample_factor(width, height)
        area = width * height * factor * factor
        if factor == 4:
            assert width * height <= _SUPERSAMPLE_4_MAX_AREA
        elif factor == 2:
            assert width * height <= _SUPERSAMPLE_2_MAX_AREA
        # Buffer penuh tidak pernah dialokasikan sekaligus di jalur berpita.
        assert area > 0


def test_banded_render_is_pixel_identical_to_a_single_pass_render() -> None:
    layer, width, height = _line_layer(1400.0, 1100.0)
    factor = _supersample_factor(width, height)
    assert factor > 1
    assert width * factor * factor * height > _MAX_BAND_PIXELS, "kasus uji harus memicu pita"

    banded = render_shape_image(layer, width, height)

    values = parse_shape_properties(layer)
    scale_x = width / values["pixel_width"] * factor
    scale_y = height / values["pixel_height"] * factor
    padding_x = values["padding"] * scale_x
    padding_y = values["padding"] * scale_y
    whole = Image.new("RGBA", (width * factor, height * factor), (0, 0, 0, 0))
    _draw_shape(
        ImageDraw.Draw(whole),
        values,
        (padding_x, padding_y, width * factor - padding_x, height * factor - padding_y),
        max(1, round(values["stroke_width"] * min(scale_x, scale_y))),
    )
    expected = whole.resize((width, height), Image.Resampling.BOX)

    assert banded.size == expected.size
    assert banded.tobytes() == expected.tobytes()


def test_large_line_still_renders_visible_ink() -> None:
    layer, width, height = _line_layer(6000.0, 4500.0)
    image = render_shape_image(layer, width, height)
    assert image.size == (width, height)
    assert image.getchannel("A").getbbox() is not None


# ---------------------------------------------------------------------------
# Penghapus pada objek besar
# ---------------------------------------------------------------------------


def _session(tmp_path: Path) -> DestructiveEraserProjectSession:
    session = DestructiveEraserProjectSession(tmp_path / "models")
    session.new_project(title="Garis", creator="Tester", width=4000, height=3000)
    return session


def test_eraser_removes_pixels_from_a_large_line(tmp_path: Path) -> None:
    session = _session(tmp_path)
    layer = session.create_object_layer("Shapes")
    line = session.create_shape_layer(
        "line",
        (100, 100),
        (3900, 2900),
        target_layer_id=layer.layer_id,
        stroke_width=24.0,
    )

    updated = session.erase_object_pixels(
        line.object_id,
        points=((2000, 1500), (2100, 1576)),
        brush_size=200,
    )

    assert updated.object_id == line.object_id
    assert updated.kind is ObjectKind.RASTER
    assert updated.properties["eraser_original_kind"] == ObjectKind.SHAPE.value
    erased = Image.open(BytesIO(session.assets[updated.asset_ref or ""])).convert("RGBA")

    original = render_shape_image(
        Layer(
            name=line.name,
            kind=LayerKind.SHAPE,
            transform=Transform(),
            properties={
                **dict(line.properties),
                "pixel_width": line.bounds.width,
                "pixel_height": line.bounds.height,
            },
        ),
        max(1, round(line.bounds.width)),
        max(1, round(line.bounds.height)),
    )
    assert sum(erased.getchannel("A").tobytes()) < sum(original.getchannel("A").tobytes())


def test_eraser_stroke_outside_the_object_is_rejected_cleanly(tmp_path: Path) -> None:
    """Goresan di luar objek harus memunculkan galat yang bisa ditangkap UI.

    Editor menangkap ``(ProjectSessionError, ValueError)``; keduanya berujung
    pada pesan status, bukan dialog crash.
    """

    session = _session(tmp_path)
    layer = session.create_object_layer("Shapes")
    rectangle = session.create_shape_layer(
        "rectangle",
        (100, 100),
        (300, 300),
        target_layer_id=layer.layer_id,
        fill_enabled=True,
    )
    with pytest.raises(ValueError):
        session.erase_object_pixels(
            rectangle.object_id,
            points=((-4000, -4000), (-3900, -3900)),
            brush_size=8,
        )


def test_local_subtract_matches_the_full_size_mask_result(tmp_path: Path) -> None:
    """Pengurangan alfa berbasis kotak-batas harus identik dengan mask penuh."""

    source = Image.new("RGBA", (900, 700), (30, 40, 50, 255))
    stroke = Image.new("L", (64, 48), 0)
    ImageDraw.Draw(stroke).ellipse((4, 4, 60, 44), fill=255)
    left, top = 400, 300

    full = source.copy()
    mask = Image.new("L", full.size, 0)
    mask.paste(stroke, (left, top))
    full.putalpha(ImageChops.subtract(full.getchannel("A"), mask))

    local = source.copy()
    region = (left, top, left + stroke.width, top + stroke.height)
    patch = local.crop(region)
    patch.putalpha(ImageChops.subtract(patch.getchannel("A"), stroke))
    local.paste(patch, region)

    assert local.tobytes() == full.tobytes()


# ---------------------------------------------------------------------------
# Uji tumbukan berbasis tinta
# ---------------------------------------------------------------------------


def test_diagonal_line_is_not_hit_in_the_empty_corner_of_its_bounding_box() -> None:
    clear_hit_mask_cache()
    line = _line_object(3000.0, 2000.0, stroke_width=8.0)
    from batikcraft_studio.imaging.affine_object import point_hits_affine_object

    corner = (2900.0, 100.0)
    assert point_hits_affine_object(line, *corner) is True
    assert precise_point_hits_object(line, {}, *corner) is False


def test_diagonal_line_is_hit_on_its_own_ink() -> None:
    clear_hit_mask_cache()
    line = _line_object(3000.0, 2000.0, stroke_width=40.0)
    on_ink = (1500.0, 1000.0)
    assert precise_point_hits_object(line, {}, *on_ink) is True


def test_point_outside_the_bounding_box_is_never_a_hit() -> None:
    clear_hit_mask_cache()
    line = _line_object(3000.0, 2000.0)
    assert precise_point_hits_object(line, {}, -50.0, -50.0) is False


def test_missing_asset_falls_back_to_bounding_box_behaviour() -> None:
    clear_hit_mask_cache()
    item = LayerObject(
        name="Raster hilang",
        kind=ObjectKind.RASTER,
        asset_ref="assets/missing.png",
        transform=Transform(x=100.0, y=100.0),
        bounds=ObjectBounds(200.0, 200.0),
    )
    assert precise_point_hits_object(item, {}, 100.0, 100.0) is True
    assert precise_point_hits_object(item, {}, 500.0, 500.0) is False
