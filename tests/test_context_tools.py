from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from batikcraft_studio.application import DestructiveEraserProjectSession
from batikcraft_studio.domain import ObjectKind
from batikcraft_studio.ui.tool_icons import available_tool_icons, render_tool_icon


def _session(tmp_path: Path) -> DestructiveEraserProjectSession:
    session = DestructiveEraserProjectSession(tmp_path / "models")
    session.new_project(
        title="Context tools",
        creator="Tester",
        width=320,
        height=240,
    )
    return session


def test_eraser_changes_existing_stroke_without_adding_overlay_object(tmp_path: Path) -> None:
    session = _session(tmp_path)
    layer = session.create_paint_layer("Paint")
    session.apply_paint_stroke(
        layer.layer_id,
        points=((80, 120), (240, 120)),
        brush_size=48,
        color="#4E2A1E",
        hardness=1.0,
    )
    project = session.require_project()
    object_id = project.active_object_id or ""
    before = project.get_object(object_id)
    before_count = project.object_count
    before_asset = before.asset_ref or ""
    before_alpha = Image.open(BytesIO(session.assets[before_asset])).convert("RGBA").getchannel("A")
    before_total = sum(before_alpha.tobytes())

    updated = session.erase_object_pixels(
        object_id,
        points=((150, 120), (170, 120)),
        brush_size=36,
        opacity=1.0,
        hardness=1.0,
    )

    assert session.require_project().object_count == before_count
    assert updated.object_id == object_id
    assert updated.kind is ObjectKind.PAINT_STROKE
    assert updated.asset_ref != before_asset
    assert all(
        item.kind is not ObjectKind.ERASER_STROKE
        for layer_item in session.require_project().layers
        for item in layer_item.objects
    )
    after_alpha = (
        Image.open(BytesIO(session.assets[updated.asset_ref or ""]))
        .convert("RGBA")
        .getchannel("A")
    )
    assert sum(after_alpha.tobytes()) < before_total

    assert session.undo() is True
    restored = session.require_project().get_object(object_id)
    assert restored.asset_ref == before_asset


def test_eraser_rasterizes_shape_and_preserves_object_identity(tmp_path: Path) -> None:
    session = _session(tmp_path)
    layer = session.create_object_layer("Shapes")
    shape = session.create_shape_layer(
        "rectangle",
        (80, 60),
        (240, 180),
        target_layer_id=layer.layer_id,
        fill_enabled=True,
    )

    updated = session.erase_object_pixels(
        shape.object_id,
        points=((150, 120), (175, 120)),
        brush_size=32,
    )

    assert updated.object_id == shape.object_id
    assert updated.kind is ObjectKind.RASTER
    assert updated.properties["eraser_original_kind"] == ObjectKind.SHAPE.value
    assert updated.asset_ref in session.assets


def test_all_context_tool_icons_are_offline_font_awesome_masks() -> None:
    names = available_tool_icons()
    assert {
        "select_tool",
        "fill_tool",
        "eraser_tool",
        "dock_tab",
        "dock_float",
    }.issubset(names)
    for name in names:
        image = render_tool_icon(name, size=24)
        assert image.size == (24, 24)
        assert image.getchannel("A").getbbox() is not None
