from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from batikcraft_studio.application import DirectStyleProjectSession
from batikcraft_studio.domain import LayerNodeKind


def _session(tmp_path: Path) -> DirectStyleProjectSession:
    session = DirectStyleProjectSession(tmp_path / "models")
    session.new_project(
        title="Direct Style",
        creator="Tester",
        width=320,
        height=240,
    )
    return session


def test_palette_auto_colors_closed_fill_and_open_stroke(tmp_path: Path) -> None:
    session = _session(tmp_path)
    layer = session.create_object_layer("Shapes")
    rectangle = session.create_shape_layer(
        "rectangle",
        (30, 30),
        (130, 110),
        target_layer_id=layer.layer_id,
    )
    line = session.create_shape_layer(
        "line",
        (160, 40),
        (260, 120),
        target_layer_id=layer.layer_id,
    )
    session.set_selected_objects([rectangle.object_id, line.object_id])

    updated = session.apply_color_to_selected("#336699", target="auto")

    assert len(updated) == 2
    rectangle_after = session.require_project().get_object(rectangle.object_id)
    line_after = session.require_project().get_object(line.object_id)
    assert rectangle_after.properties["fill_color"] == "#336699"
    assert rectangle_after.properties["fill_enabled"] is True
    assert line_after.properties["stroke_color"] == "#336699"
    assert line_after.properties["stroke_enabled"] is True


def test_outline_visibility_and_width_are_one_undoable_style_change(tmp_path: Path) -> None:
    session = _session(tmp_path)
    layer = session.create_object_layer("Shapes")
    first = session.create_default_shape_layer("rectangle", target_layer_id=layer.layer_id)
    second = session.create_default_shape_layer("ellipse", target_layer_id=layer.layer_id)
    session.set_selected_objects([first.object_id, second.object_id])

    session.set_selected_shape_stroke_enabled(False)
    assert all(
        session.require_project().get_object(item.object_id).properties["stroke_enabled"] is False
        for item in (first, second)
    )
    assert session.undo() is True
    assert all(
        session.require_project().get_object(item.object_id).properties["stroke_enabled"] is True
        for item in (first, second)
    )

    session.set_selected_objects([first.object_id, second.object_id])
    session.set_selected_shape_stroke_width(9.5)
    assert all(
        session.require_project().get_object(item.object_id).properties["stroke_width"] == 9.5
        for item in (first, second)
    )


def test_fill_tool_creates_separate_fill_for_one_closed_paint_loop(tmp_path: Path) -> None:
    session = _session(tmp_path)
    layer = session.create_paint_layer("Closed Loop")
    session.apply_paint_stroke(
        layer.layer_id,
        points=((60, 60), (180, 60), (180, 160), (60, 160), (60, 60)),
        brush_size=10,
        color="#4E2A1E",
        hardness=1.0,
        smoothing=0.4,
    )
    stroke = session.require_project().get_object(
        session.require_project().active_object_id or ""
    )
    before = session.require_project().object_count

    created = session.fill_closed_object(stroke.object_id, "#D9A566")

    assert len(created) == 2
    assert session.require_project().object_count == before + 1
    fill = created[0]
    assert fill.properties["fill_source_object_id"] == stroke.object_id
    with Image.open(BytesIO(session.assets[fill.asset_ref or ""])) as image:
        image.load()
        assert image.getchannel("A").getbbox() is not None
    assert session.undo() is True
    assert session.require_project().object_count == before


def test_layer_and_object_drag_drop_are_undoable(tmp_path: Path) -> None:
    session = _session(tmp_path)
    folder = session.create_folder("Folder")
    first_layer = session.create_object_layer("First")
    second_layer = session.create_object_layer("Second")
    shape = session.create_default_shape_layer(
        "polygon",
        target_layer_id=first_layer.layer_id,
    )

    moved_layer_iid = session.move_tree_node(
        f"layer:{first_layer.layer_id}",
        f"layer:{folder.layer_id}",
    )
    assert moved_layer_iid == f"layer:{first_layer.layer_id}"
    assert session.require_project().get_layer(first_layer.layer_id).parent_id == folder.layer_id
    assert session.undo() is True
    assert session.require_project().get_layer(first_layer.layer_id).parent_id is None

    moved_object_iid = session.move_tree_node(
        f"object:{shape.object_id}",
        f"layer:{second_layer.layer_id}",
    )
    assert moved_object_iid == f"object:{shape.object_id}"
    assert session.require_project().object_layer_id(shape.object_id) == second_layer.layer_id
    assert session.undo() is True
    assert session.require_project().object_layer_id(shape.object_id) == first_layer.layer_id


def test_direct_style_persists_after_save_and_reopen(tmp_path: Path) -> None:
    session = _session(tmp_path)
    layer = session.create_object_layer("Shapes")
    shape = session.create_default_shape_layer("polygon", target_layer_id=layer.layer_id)
    session.set_selected_objects([shape.object_id])
    session.apply_color_to_selected("#B13A45", target="fill")
    session.set_selected_shape_stroke_enabled(False)
    path = tmp_path / "direct-style.batikcraft"
    session.save_as(path)

    reopened = DirectStyleProjectSession(tmp_path / "models-2")
    reopened.open_project(path)
    restored = reopened.require_project().get_object(shape.object_id)

    assert restored.properties["fill_color"] == "#B13A45"
    assert restored.properties["fill_enabled"] is True
    assert restored.properties["stroke_enabled"] is False
    assert reopened.require_project().get_layer(layer.layer_id).node_kind is LayerNodeKind.LAYER
