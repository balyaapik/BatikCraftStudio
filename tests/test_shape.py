from __future__ import annotations

import pytest

from batikcraft_studio.domain import Layer, LayerKind, Transform
from batikcraft_studio.imaging.shape import (
    ShapeError,
    build_shape_geometry,
    render_shape_image,
)


def _layer_from_geometry(shape_type: str, **kwargs: object) -> Layer:
    geometry = build_shape_geometry(shape_type, (10, 20), (110, 80), **kwargs)
    return Layer(
        name=shape_type.title(),
        kind=LayerKind.SHAPE,
        transform=Transform(x=geometry.center_x, y=geometry.center_y),
        properties=dict(geometry.properties),
    )


def test_rectangle_geometry_records_editable_bounds_and_style() -> None:
    geometry = build_shape_geometry(
        "rectangle",
        (10, 20),
        (110, 80),
        fill_color="#d9a566",
        stroke_color="#273043",
        stroke_width=6,
    )

    assert geometry.center_x == 60
    assert geometry.center_y == 50
    assert geometry.properties["geometry_width"] == 100
    assert geometry.properties["geometry_height"] == 60
    assert geometry.properties["fill_color"] == "#D9A566"
    assert geometry.properties["stroke_color"] == "#273043"
    assert geometry.properties["pixel_width"] > 100


def test_shift_constraint_makes_square_and_snaps_line_to_45_degrees() -> None:
    square = build_shape_geometry(
        "rectangle",
        (0, 0),
        (90, 40),
        constrain=True,
    )
    line = build_shape_geometry(
        "line",
        (0, 0),
        (80, 60),
        constrain=True,
    )

    assert square.properties["geometry_width"] == square.properties["geometry_height"]
    line_width = float(line.properties["geometry_width"])
    line_height = float(line.properties["geometry_height"])
    assert line_width == pytest.approx(line_height)


def test_alt_modifier_builds_shape_from_center() -> None:
    geometry = build_shape_geometry(
        "ellipse",
        (50, 50),
        (80, 70),
        from_center=True,
    )

    assert geometry.center_x == 50
    assert geometry.center_y == 50
    assert geometry.properties["geometry_width"] == 60
    assert geometry.properties["geometry_height"] == 40


def test_render_shape_image_draws_fill_and_stroke_with_transparency_outside() -> None:
    layer = _layer_from_geometry(
        "ellipse",
        fill_color="#D9A566",
        stroke_color="#273043",
        stroke_width=5,
    )

    image = render_shape_image(layer, 220, 140)

    assert image.mode == "RGBA"
    assert image.size == (220, 140)
    assert image.getpixel((110, 70))[3] == 255
    assert image.getpixel((0, 0))[3] == 0


def test_polygon_renderer_respects_requested_side_count() -> None:
    layer = _layer_from_geometry("polygon", polygon_sides=5)

    image = render_shape_image(layer, 160, 120)

    assert image.getchannel("A").getextrema()[1] == 255
    assert layer.properties["polygon_sides"] == 5


@pytest.mark.parametrize(
    ("shape_type", "kwargs", "message"),
    (
        ("triangle-ish", {}, "must be one of"),
        ("rectangle", {"stroke_enabled": False, "fill_enabled": False}, "fill, stroke"),
        ("polygon", {"polygon_sides": 2}, "between 3 and 12"),
        ("line", {"stroke_enabled": False}, "require an enabled stroke"),
    ),
)
def test_shape_geometry_rejects_invalid_input(
    shape_type: str,
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ShapeError, match=message):
        build_shape_geometry(shape_type, (0, 0), (40, 30), **kwargs)
