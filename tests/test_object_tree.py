from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.domain import LayerNodeKind, ProjectValidationError
from batikcraft_studio.imaging import render_project_preview, transformed_object_bounds


def _asset_png(width: int = 80, height: int = 60) -> bytes:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 6, width - 8, height - 6), fill=(98, 48, 28, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_layer_can_hold_multiple_independently_selectable_objects() -> None:
    session = ProjectSession()
    project = session.new_project(title="Objek", creator="Perajin", width=500, height=400)
    layer = session.create_object_layer("Motif Pokok")

    first = session.import_batik_asset(
        "kawung.png",
        _asset_png(),
        target_layer_id=layer.layer_id,
        default_category="motif-pokok",
    )
    second = session.import_batik_asset(
        "truntum.png",
        _asset_png(64, 64),
        target_layer_id=layer.layer_id,
        default_category="motif-pokok",
    )

    refreshed = project.get_layer(layer.layer_id)
    assert [item.object_id for item in refreshed.objects] == [first.object_id, second.object_id]
    assert len(project.layers) == 1
    assert project.active_layer_id == layer.layer_id
    assert project.active_object_id == second.object_id


def test_folder_tree_supports_sublayers_and_rejects_cycles() -> None:
    session = ProjectSession()
    project = session.new_project(title="Tree", creator="Perajin")
    root = session.create_folder("Motif Utama")
    child_folder = session.create_folder("Isen", parent_id=root.layer_id)
    layer = session.create_object_layer("Cecek", parent_id=child_folder.layer_id)

    assert project.children_of(root.layer_id) == (child_folder,)
    assert project.children_of(child_folder.layer_id) == (layer,)
    assert child_folder.node_kind is LayerNodeKind.GROUP
    with pytest.raises(ProjectValidationError, match="cycle"):
        session.move_layer_to_folder(root.layer_id, child_folder.layer_id)


def test_completed_brush_strokes_are_cropped_objects_not_full_canvas() -> None:
    session = ProjectSession()
    project = session.new_project(title="Canting", creator="Perajin", width=800, height=600)
    layer = session.create_paint_layer()

    session.apply_paint_stroke(
        layer.layer_id,
        points=[(100, 120), (140, 145), (190, 150)],
        brush_size=24,
        color="#5A2B1E",
        smoothing=0.4,
    )
    session.apply_paint_stroke(
        layer.layer_id,
        points=[(420, 300), (450, 330)],
        brush_size=18,
        color="#243B66",
    )

    objects = project.get_layer(layer.layer_id).objects
    assert len(objects) == 2
    assert all(item.bounds.width < project.canvas.width for item in objects)
    assert all(item.bounds.height < project.canvas.height for item in objects)
    left, top, right, bottom = transformed_object_bounds(objects[0])
    assert right - left == pytest.approx(objects[0].bounds.width)
    assert bottom - top == pytest.approx(objects[0].bounds.height)


def test_cermin_motif_creates_many_objects_in_one_layer_and_one_undo() -> None:
    session = ProjectSession()
    project = session.new_project(title="Kawung", creator="Perajin", width=600, height=400)

    objects = session.cap_motif(
        "kawung",
        (180, 120),
        ukuran=160,
        susun="cermin_empat",
    )

    assert len(objects) == 4
    assert len(project.layers) == 1
    assert len(project.layers[0].objects) == 4
    assert len({item.asset_ref for item in objects}) == 1
    assert session.undo() is True
    assert session.require_project().layers == ()
    assert session.redo() is True
    assert len(session.require_project().layers[0].objects) == 4


def test_object_layers_render_and_survive_save_reopen(tmp_path: Path) -> None:
    session = ProjectSession()
    session.new_project(title="Archive", creator="Perajin", width=320, height=240)
    folder = session.create_folder("Ragam Hias")
    layer = session.create_object_layer("Ornamen", parent_id=folder.layer_id)
    item = session.import_batik_asset(
        "ornamen.png",
        _asset_png(),
        target_layer_id=layer.layer_id,
    )
    session.move_object(item.object_id, x=140, y=100)

    rendered = render_project_preview(
        session.require_project(),
        session.assets,
        max_width=320,
        max_height=240,
    )
    assert rendered.image.getbbox() == (0, 0, 320, 240)

    path = tmp_path / "tree.batikcraft"
    session.save_as(path)
    reopened = ProjectSession()
    project = reopened.open_project(path)
    assert project.schema_version == "1.1"
    assert project.children_of(folder.layer_id)[0].layer_id == layer.layer_id
    assert project.get_object(item.object_id).transform.x == 140
