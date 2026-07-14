from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.domain import LayerObject, ObjectBounds, ObjectKind, Transform
from batikcraft_studio.imaging.affine_object import (
    SHEAR_X_KEY,
    SHEAR_Y_KEY,
    inverse_transform_point,
    object_axis_aligned_bounds,
    object_corners,
    point_hits_affine_object,
    transform_local_point,
)
from batikcraft_studio.imaging.renderer import render_project_preview


def _asset_png(width: int = 80, height: int = 50) -> bytes:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 4, width - 5, height - 5), fill=(98, 48, 28, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _affine_item() -> LayerObject:
    return LayerObject(
        name="Affine",
        kind=ObjectKind.RASTER,
        asset_ref="assets/a.png",
        transform=Transform(
            x=140,
            y=110,
            rotation_degrees=31,
            scale_x=1.4,
            scale_y=0.75,
        ),
        bounds=ObjectBounds(80, 50),
        properties={SHEAR_X_KEY: 0.45, SHEAR_Y_KEY: -0.2},
    )


def test_affine_inverse_and_hit_test_match_transformed_corners() -> None:
    item = _affine_item()
    local = (17.0, -9.0)
    world = transform_local_point(item, *local)

    recovered = inverse_transform_point(item, *world)

    assert recovered is not None
    assert recovered == pytest.approx(local)
    assert point_hits_affine_object(item, *world) is True
    assert point_hits_affine_object(item, 500, 500) is False


def test_axis_aligned_bounds_enclose_every_affine_corner() -> None:
    item = _affine_item()
    corners = object_corners(item)
    left, top, right, bottom = object_axis_aligned_bounds(item)

    assert all(left <= x <= right and top <= y <= bottom for x, y in corners)
    assert right - left > 80
    assert bottom - top > 50


def test_renderer_applies_object_shear_and_preserves_canvas() -> None:
    session = ProjectSession()
    project = session.new_project(title="Affine", creator="Perajin", width=320, height=240)
    layer = session.create_object_layer("Motif")
    item = session.import_batik_asset(
        "motif.png",
        _asset_png(),
        target_layer_id=layer.layer_id,
    )
    original = item.transform
    session.begin_interactive_object_transform(item.object_id)
    session.preview_interactive_object_transform(
        item.object_id,
        transform=Transform(
            x=160,
            y=120,
            rotation_degrees=24,
            scale_x=1.2,
            scale_y=0.8,
        ),
        shear_x=0.6,
        shear_y=-0.15,
    )
    session.commit_interactive_object_transform()

    rendered = render_project_preview(
        project,
        session.assets,
        max_width=320,
        max_height=240,
    )

    assert rendered.image.size == (320, 240)
    changed = project.get_object(item.object_id)
    assert changed.transform != original
    assert changed.properties[SHEAR_X_KEY] == pytest.approx(0.6)
    assert changed.properties[SHEAR_Y_KEY] == pytest.approx(-0.15)


def test_many_live_previews_commit_as_one_undo_step() -> None:
    session = ProjectSession()
    project = session.new_project(title="Live", creator="Perajin", width=400, height=300)
    layer = session.create_object_layer("Motif")
    item = session.import_batik_asset(
        "motif.png",
        _asset_png(),
        target_layer_id=layer.layer_id,
    )
    start = item.transform

    session.begin_interactive_object_transform(item.object_id)
    for step in range(25):
        session.preview_interactive_object_transform(
            item.object_id,
            transform=Transform(
                x=start.x + step * 2,
                y=start.y + step,
                rotation_degrees=step * 3,
                scale_x=1 + step / 50,
                scale_y=1 - step / 100,
            ),
            shear_x=step / 100,
            shear_y=-step / 200,
        )
    assert session.commit_interactive_object_transform() is True
    final = project.get_object(item.object_id)
    assert final.transform != start

    assert session.undo() is True
    restored = session.require_project().get_object(item.object_id)
    assert restored.transform == start
    assert SHEAR_X_KEY not in restored.properties
    assert session.undo() is True  # undo original import, proving only one transform entry existed
