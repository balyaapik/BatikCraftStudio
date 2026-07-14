from __future__ import annotations

from pathlib import Path

from batikcraft_studio.application import ShapeProjectSession
from batikcraft_studio.domain import LayerKind
from batikcraft_studio.imaging import render_project_preview


def test_create_shape_layer_adds_non_asset_editable_layer() -> None:
    session = ShapeProjectSession()
    project = session.new_project(title="Shapes", creator="Creator", width=400, height=300)

    layer = session.create_shape_layer(
        "rectangle",
        (50, 60),
        (250, 180),
        fill_color="#D9A566",
        stroke_color="#273043",
        stroke_width=5,
    )

    assert layer.kind is LayerKind.SHAPE
    assert layer.asset_ref is None
    assert layer.transform.x == 150
    assert layer.transform.y == 120
    assert layer.properties["shape_type"] == "rectangle"
    assert project.active_layer_id == layer.layer_id
    assert dict(session.assets) == {}


def test_shape_creation_and_update_are_undoable() -> None:
    session = ShapeProjectSession()
    project = session.new_project(title="Shapes", creator="Creator", width=300, height=300)

    layer = session.create_default_shape_layer("ellipse")
    created_revision = project.revision
    updated = session.update_shape_layer(
        layer.layer_id,
        geometry_width=180,
        geometry_height=120,
        fill_color="#AA5533",
        stroke_width=8,
    )

    assert updated.properties["geometry_width"] == 180
    assert updated.properties["fill_color"] == "#AA5533"
    assert project.revision == created_revision + 1

    assert session.undo() is True
    restored = session.require_project().get_layer(layer.layer_id)
    assert restored.properties["geometry_width"] != 180

    assert session.redo() is True
    redone = session.require_project().get_layer(layer.layer_id)
    assert redone.properties["geometry_width"] == 180
    assert redone.properties["stroke_width"] == 8


def test_default_shape_layer_is_centered_and_renderable() -> None:
    session = ShapeProjectSession()
    project = session.new_project(title="Shapes", creator="Creator", width=500, height=400)

    layer = session.create_default_shape_layer("polygon", polygon_sides=5)
    preview = render_project_preview(project, session.assets, max_width=500, max_height=400)

    assert layer.transform.x == 250
    assert layer.transform.y == 200
    assert preview.image.getchannel("A").getextrema() == (255, 255)
    center = preview.image.getpixel((250, 200))
    assert center[:3] == (217, 165, 102)


def test_shape_layer_survives_save_and_reopen(tmp_path: Path) -> None:
    session = ShapeProjectSession()
    session.new_project(title="Shapes", creator="Creator", width=320, height=240)
    layer = session.create_shape_layer(
        "line",
        (20, 30),
        (280, 210),
        stroke_color="#336699",
        stroke_width=7,
        fill_enabled=False,
    )
    destination = tmp_path / "shapes.batikcraft"

    session.save_as(destination)
    reopened = ShapeProjectSession()
    reopened.open_project(destination)
    stored = reopened.require_project().get_layer(layer.layer_id)

    assert stored.kind is LayerKind.SHAPE
    assert stored.asset_ref is None
    assert stored.properties["shape_type"] == "line"
    assert stored.properties["stroke_color"] == "#336699"
    assert stored.properties["stroke_width"] == 7
    assert dict(reopened.assets) == {}


def test_context_menu_commands_can_create_paint_and_shape_layers_through_one_session() -> None:
    session = ShapeProjectSession()
    project = session.new_project(title="Layers", creator="Creator", width=256, height=256)

    paint = session.create_paint_layer()
    shape = session.create_default_shape_layer("rectangle")

    assert paint.kind is LayerKind.PAINT
    assert shape.kind is LayerKind.SHAPE
    assert len(project.layers) == 2
    assert project.active_layer_id == shape.layer_id
