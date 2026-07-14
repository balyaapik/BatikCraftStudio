from __future__ import annotations

from pathlib import Path

from batikcraft_studio.application import CanvasStructureProjectSession
from batikcraft_studio.domain import LayerNodeKind, ObjectKind
from batikcraft_studio.ui.canvas_structure_editor import (
    choose_ruler_step,
    format_ruler_value,
)


def test_multiple_shapes_share_one_active_layer_container(tmp_path: Path) -> None:
    session = CanvasStructureProjectSession(tmp_path / "models")
    session.new_project(title="Layers", creator="Tester", width=600, height=400)
    layer = session.create_object_layer("Layer Komposisi")

    rectangle = session.create_shape_layer("rectangle", (40, 40), (180, 160))
    ellipse = session.create_shape_layer("ellipse", (220, 60), (380, 190))

    project = session.require_project()
    refreshed = project.get_layer(layer.layer_id)
    assert refreshed.node_kind is LayerNodeKind.LAYER
    assert refreshed.asset_ref is None
    assert tuple(item.object_id for item in refreshed.objects) == (
        rectangle.object_id,
        ellipse.object_id,
    )
    assert all(item.kind is ObjectKind.SHAPE for item in refreshed.objects)
    assert project.object_layer_id(rectangle.object_id) == layer.layer_id
    assert project.object_layer_id(ellipse.object_id) == layer.layer_id


def test_shape_created_while_folder_selected_gets_child_layer(tmp_path: Path) -> None:
    session = CanvasStructureProjectSession(tmp_path / "models")
    session.new_project(title="Folders", creator="Tester", width=500, height=500)
    folder = session.create_folder("Folder Flora")

    rectangle = session.create_shape_layer("rectangle", (80, 80), (240, 220))

    project = session.require_project()
    owner = project.get_layer(project.object_layer_id(rectangle.object_id))
    assert owner.node_kind is LayerNodeKind.LAYER
    assert owner.parent_id == folder.layer_id
    assert rectangle.object_id in {item.object_id for item in owner.objects}


def test_fill_color_only_changes_selected_closed_shapes(tmp_path: Path) -> None:
    session = CanvasStructureProjectSession(tmp_path / "models")
    session.new_project(title="Fill", creator="Tester", width=500, height=400)
    session.create_object_layer("Layer Bentuk")
    rectangle = session.create_shape_layer(
        "rectangle",
        (40, 40),
        (180, 160),
        fill_enabled=False,
    )
    line = session.create_shape_layer(
        "line",
        (220, 80),
        (390, 180),
        fill_enabled=False,
    )
    session.set_selected_objects([rectangle.object_id, line.object_id])

    updated = session.set_selected_closed_shape_fill("#336699")

    project = session.require_project()
    refreshed_rectangle = project.get_object(rectangle.object_id)
    refreshed_line = project.get_object(line.object_id)
    assert tuple(item.object_id for item in updated) == (rectangle.object_id,)
    assert refreshed_rectangle.properties["fill_enabled"] is True
    assert refreshed_rectangle.properties["fill_color"] == "#336699"
    assert refreshed_line.properties["fill_enabled"] is False
    assert refreshed_line.properties["shape_type"] == "line"


def test_selected_objects_move_between_layer_containers_as_one_command(
    tmp_path: Path,
) -> None:
    session = CanvasStructureProjectSession(tmp_path / "models")
    session.new_project(title="Move", creator="Tester", width=600, height=400)
    source = session.create_object_layer("Layer Sumber")
    rectangle = session.create_shape_layer("rectangle", (30, 30), (150, 140))
    ellipse = session.create_shape_layer("ellipse", (190, 40), (330, 170))
    target = session.create_object_layer("Layer Tujuan")
    session.set_selected_objects([rectangle.object_id, ellipse.object_id])

    moved = session.move_selected_objects_to_layer(target.layer_id)

    project = session.require_project()
    assert {item.object_id for item in moved} == {
        rectangle.object_id,
        ellipse.object_id,
    }
    assert project.get_layer(source.layer_id).objects == ()
    assert {item.object_id for item in project.get_layer(target.layer_id).objects} == {
        rectangle.object_id,
        ellipse.object_id,
    }
    assert session.undo() is True
    restored = session.require_project()
    assert {item.object_id for item in restored.get_layer(source.layer_id).objects} == {
        rectangle.object_id,
        ellipse.object_id,
    }


def test_layer_folder_and_shape_objects_survive_save_reopen(tmp_path: Path) -> None:
    session = CanvasStructureProjectSession(tmp_path / "models")
    session.new_project(title="Persist", creator="Tester", width=500, height=500)
    folder = session.create_folder("Folder Utama")
    rectangle = session.create_shape_layer("rectangle", (80, 80), (260, 240))
    ellipse = session.create_shape_layer("ellipse", (280, 100), (430, 260))
    session.set_selected_objects([rectangle.object_id, ellipse.object_id])
    session.set_selected_closed_shape_fill("#A45B3B")
    path = tmp_path / "containers.batikcraft"
    session.save_as(path)

    reopened = CanvasStructureProjectSession(tmp_path / "models-reopened")
    reopened.open_project(path)
    project = reopened.require_project()
    rectangle_owner = project.get_layer(project.object_layer_id(rectangle.object_id))

    assert rectangle_owner.parent_id == folder.layer_id
    assert len(rectangle_owner.objects) == 2
    assert project.get_object(rectangle.object_id).properties["fill_color"] == "#A45B3B"
    assert project.get_object(ellipse.object_id).properties["fill_color"] == "#A45B3B"


def test_ruler_step_uses_readable_one_two_five_intervals() -> None:
    assert choose_ruler_step(1.0) == 100.0
    assert choose_ruler_step(2.0) == 50.0
    assert choose_ruler_step(0.5) == 200.0
    assert choose_ruler_step(0.0) == 100.0
    assert format_ruler_value(100.0) == "100"
    assert format_ruler_value(12.5) == "12.5"
