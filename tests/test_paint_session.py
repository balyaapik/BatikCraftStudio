from __future__ import annotations

import pytest

from batikcraft_studio.application import (
    LayerLockedError,
    PaintLayerError,
    PaintProjectSession,
)
from batikcraft_studio.domain import LayerKind, ObjectKind


def test_create_paint_layer_adds_empty_object_container() -> None:
    session = PaintProjectSession()
    project = session.new_project(title="Paint", creator="Creator", width=80, height=60)

    layer = session.create_paint_layer()

    assert layer.kind is LayerKind.PAINT
    assert layer.asset_ref is None
    assert layer.objects == ()
    assert layer.properties["object_container"] is True
    assert layer.properties["source_format"] == "PAINT_OBJECTS"
    assert project.active_layer_id == layer.layer_id


def test_one_refined_paint_stroke_is_one_undoable_object() -> None:
    session = PaintProjectSession()
    project = session.new_project(title="Paint", creator="Creator", width=64, height=64)
    layer = session.create_paint_layer()

    updated = session.apply_paint_stroke(
        layer.layer_id,
        points=((8, 8), (30, 48), (56, 56)),
        brush_size=7,
        color="#AA3300",
        opacity=0.65,
        hardness=0.4,
        smoothing=0.5,
    )

    assert len(updated.objects) == 1
    stroke = updated.objects[0]
    assert stroke.kind is ObjectKind.PAINT_STROKE
    assert stroke.asset_ref is not None
    assert stroke.asset_ref in session.assets
    assert stroke.bounds.width < project.canvas.width
    assert stroke.bounds.height < project.canvas.height
    assert updated.properties["stroke_count"] == 1
    assert updated.properties["last_tool"] == "brush"
    assert updated.properties["last_brush_size"] == 7.0
    assert updated.properties["last_brush_opacity"] == 0.65
    assert updated.properties["last_brush_hardness"] == 0.4
    assert updated.properties["last_brush_smoothing"] == 0.5

    assert session.undo() is True
    restored = session.require_project().get_layer(layer.layer_id)
    assert restored.objects == ()
    assert stroke.asset_ref not in session.assets
    assert restored.properties["stroke_count"] == 0

    assert session.redo() is True
    redone = session.require_project().get_layer(layer.layer_id)
    assert len(redone.objects) == 1
    assert redone.objects[0].asset_ref == stroke.asset_ref
    assert stroke.asset_ref in session.assets
    assert redone.properties["last_brush_hardness"] == 0.4


def test_eraser_is_a_separate_mask_object_and_records_tool() -> None:
    session = PaintProjectSession()
    session.new_project(title="Paint", creator="Creator", width=48, height=48)
    layer = session.create_paint_layer()
    session.apply_paint_stroke(
        layer.layer_id,
        points=((4, 24), (44, 24)),
        brush_size=13,
        color="#112233",
    )

    updated = session.apply_paint_stroke(
        layer.layer_id,
        points=((24, 12), (24, 36)),
        brush_size=9,
        color="#000000",
        erase=True,
        opacity=0.5,
        hardness=0.75,
    )

    assert len(updated.objects) == 2
    assert updated.objects[0].kind is ObjectKind.PAINT_STROKE
    assert updated.objects[1].kind is ObjectKind.ERASER_STROKE
    assert updated.objects[0].asset_ref != updated.objects[1].asset_ref
    assert updated.properties["stroke_count"] == 2
    assert updated.properties["last_tool"] == "eraser"
    assert updated.properties["last_brush_opacity"] == 0.5
    assert updated.properties["last_brush_hardness"] == 0.75


def test_ensure_active_paint_layer_reuses_editable_aligned_layer() -> None:
    session = PaintProjectSession()
    project = session.new_project(title="Paint", creator="Creator", width=32, height=32)
    layer = session.create_paint_layer()

    returned = session.ensure_active_paint_layer()

    assert returned.layer_id == layer.layer_id
    assert len(project.layers) == 1


def test_ensure_active_paint_layer_creates_new_layer_when_active_is_locked() -> None:
    session = PaintProjectSession()
    project = session.new_project(title="Paint", creator="Creator", width=32, height=32)
    locked = session.create_paint_layer()
    session.set_layer_locked(locked.layer_id, True)

    returned = session.ensure_active_paint_layer()

    assert returned.layer_id != locked.layer_id
    assert returned.kind is LayerKind.PAINT
    assert len(project.layers) == 2


def test_paint_stroke_rejects_locked_layer() -> None:
    session = PaintProjectSession()
    session.new_project(title="Paint", creator="Creator", width=32, height=32)
    layer = session.create_paint_layer()
    session.set_layer_locked(layer.layer_id, True)

    with pytest.raises(LayerLockedError):
        session.apply_paint_stroke(
            layer.layer_id,
            points=((4, 4),),
            brush_size=5,
            color="#000000",
        )


def test_paint_stroke_rejects_transformed_paint_container() -> None:
    session = PaintProjectSession()
    session.new_project(title="Paint", creator="Creator", width=32, height=32)
    layer = session.create_paint_layer()
    session.update_layer_transform(layer.layer_id, rotation_degrees=15)

    with pytest.raises(PaintLayerError, match="container harus tetap"):
        session.apply_paint_stroke(
            layer.layer_id,
            points=((4, 4),),
            brush_size=5,
            color="#000000",
        )
