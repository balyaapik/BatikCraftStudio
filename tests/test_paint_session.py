from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from batikcraft_studio.application import (
    LayerLockedError,
    PaintLayerError,
    PaintProjectSession,
)
from batikcraft_studio.domain import LayerKind


def _alpha_extrema(content: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(content)) as source:
        source.load()
        return source.convert("RGBA").getchannel("A").getextrema()


def test_create_paint_layer_adds_full_canvas_transparent_asset() -> None:
    session = PaintProjectSession()
    project = session.new_project(title="Paint", creator="Creator", width=80, height=60)

    layer = session.create_paint_layer()

    assert layer.kind is LayerKind.PAINT
    assert layer.transform.x == 40
    assert layer.transform.y == 30
    assert layer.properties["pixel_width"] == 80
    assert layer.properties["pixel_height"] == 60
    assert project.active_layer_id == layer.layer_id
    assert layer.asset_ref is not None
    assert _alpha_extrema(session.assets[layer.asset_ref]) == (0, 0)


def test_one_refined_paint_stroke_is_one_undoable_history_entry() -> None:
    session = PaintProjectSession()
    project = session.new_project(title="Paint", creator="Creator", width=64, height=64)
    layer = session.create_paint_layer()
    assert layer.asset_ref is not None
    before = session.assets[layer.asset_ref]
    before_revision = project.revision

    updated = session.apply_paint_stroke(
        layer.layer_id,
        points=((8, 8), (30, 48), (56, 56)),
        brush_size=7,
        color="#AA3300",
        opacity=0.65,
        hardness=0.4,
        smoothing=0.5,
    )
    after = session.assets[layer.asset_ref]

    assert after != before
    assert updated.properties["stroke_count"] == 1
    assert updated.properties["last_tool"] == "brush"
    assert updated.properties["last_brush_size"] == 7.0
    assert updated.properties["last_brush_opacity"] == 0.65
    assert updated.properties["last_brush_hardness"] == 0.4
    assert updated.properties["last_brush_smoothing"] == 0.5
    assert project.revision == before_revision + 1

    assert session.undo() is True
    restored = session.require_project().get_layer(layer.layer_id)
    assert session.assets[layer.asset_ref] == before
    assert restored.properties["stroke_count"] == 0

    assert session.redo() is True
    redone = session.require_project().get_layer(layer.layer_id)
    assert session.assets[layer.asset_ref] == after
    assert redone.properties["stroke_count"] == 1
    assert redone.properties["last_brush_hardness"] == 0.4


def test_eraser_updates_same_asset_and_records_tool() -> None:
    session = PaintProjectSession()
    session.new_project(title="Paint", creator="Creator", width=48, height=48)
    layer = session.create_paint_layer()
    assert layer.asset_ref is not None
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

    assert updated.asset_ref == layer.asset_ref
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


def test_paint_stroke_rejects_transformed_paint_layer() -> None:
    session = PaintProjectSession()
    session.new_project(title="Paint", creator="Creator", width=32, height=32)
    layer = session.create_paint_layer()
    session.update_layer_transform(layer.layer_id, rotation_degrees=15)

    with pytest.raises(PaintLayerError, match="centered, unrotated, and unscaled"):
        session.apply_paint_stroke(
            layer.layer_id,
            points=((4, 4),),
            brush_size=5,
            color="#000000",
        )
