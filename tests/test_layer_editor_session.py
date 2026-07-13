from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from batikcraft_studio.application import LayerLockedError, ProjectSession


def _png_bytes(
    *,
    size: tuple[int, int] = (40, 20),
    color: tuple[int, int, int, int] = (80, 140, 210, 255),
) -> bytes:
    image = Image.new("RGBA", size, color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _session_with_project() -> ProjectSession:
    session = ProjectSession()
    session.new_project(
        title="Layer Test",
        creator="Tester",
        width=200,
        height=100,
        background_color="#FFFFFF",
    )
    return session


def test_import_raster_adds_centered_layer_and_normalized_asset() -> None:
    session = _session_with_project()

    layer = session.import_raster_image("sample.png", _png_bytes())

    assert session.project is not None
    assert session.project.active_layer_id == layer.layer_id
    assert layer.transform.x == 100
    assert layer.transform.y == 50
    assert layer.transform.scale_x == 1
    assert layer.transform.scale_y == 1
    assert layer.properties["pixel_width"] == 40
    assert layer.properties["pixel_height"] == 20
    assert layer.properties["source_format"] == "PNG"
    assert layer.asset_ref is not None
    assert session.assets[layer.asset_ref].startswith(b"\x89PNG")
    assert session.is_dirty
    assert session.can_undo


def test_large_import_is_scaled_to_fit_canvas() -> None:
    session = _session_with_project()

    layer = session.import_raster_image("large.png", _png_bytes(size=(400, 200)))

    assert layer.transform.scale_x == pytest.approx(0.325)
    assert layer.transform.scale_y == pytest.approx(0.325)


def test_transform_visibility_lock_and_order_commands() -> None:
    session = _session_with_project()
    first = session.import_raster_image("first.png", _png_bytes(color=(255, 0, 0, 255)))
    second = session.import_raster_image("second.png", _png_bytes(color=(0, 255, 0, 255)))

    updated = session.update_layer_transform(
        second.layer_id,
        x=120,
        y=45,
        rotation_degrees=30,
        scale_x=0.5,
        scale_y=-0.5,
    )
    assert updated.transform.x == 120
    assert updated.transform.rotation_degrees == 30
    assert updated.transform.scale_y == -0.5

    hidden = session.set_layer_visibility(second.layer_id, False)
    assert hidden.visible is False
    locked = session.set_layer_locked(second.layer_id, True)
    assert locked.locked is True
    with pytest.raises(LayerLockedError):
        session.move_layer(second.layer_id, x=0, y=0)
    with pytest.raises(LayerLockedError):
        session.delete_layer(second.layer_id)

    assert session.move_layer_down(second.layer_id)
    assert session.project is not None
    assert session.project.layers[0].layer_id == second.layer_id
    assert session.project.layers[1].layer_id == first.layer_id


def test_duplicate_shares_asset_until_last_reference_is_deleted() -> None:
    session = _session_with_project()
    original = session.import_raster_image("object.png", _png_bytes())
    duplicate = session.duplicate_layer(original.layer_id)

    assert duplicate.asset_ref == original.asset_ref
    assert len(session.assets) == 1
    session.delete_layer(original.layer_id)
    assert len(session.assets) == 1
    session.delete_layer(duplicate.layer_id)
    assert len(session.assets) == 0


def test_undo_and_redo_restore_project_and_asset_bytes() -> None:
    session = _session_with_project()

    imported = session.import_raster_image("object.png", _png_bytes())
    asset_ref = imported.asset_ref
    assert asset_ref is not None
    assert len(session.require_project().layers) == 1
    assert asset_ref in session.assets

    assert session.undo()
    assert len(session.require_project().layers) == 0
    assert asset_ref not in session.assets
    assert session.can_redo

    assert session.redo()
    assert len(session.require_project().layers) == 1
    assert asset_ref in session.assets
    assert session.require_project().active_layer_id == imported.layer_id


def test_selection_does_not_create_history_entry() -> None:
    session = _session_with_project()
    layer = session.import_raster_image("object.png", _png_bytes())
    assert session.undo()
    assert session.redo()
    assert session.can_undo
    session.select_layer(None)
    session.select_layer(layer.layer_id)

    assert session.undo()
    assert len(session.require_project().layers) == 0


def test_save_and_reopen_preserves_raster_layer_and_asset(tmp_path: Path) -> None:
    session = _session_with_project()
    layer = session.import_raster_image("object.png", _png_bytes())
    destination = tmp_path / "layer-project.batikcraft"

    session.save_as(destination)
    reopened = ProjectSession()
    reopened.open_project(destination)

    assert reopened.project is not None
    assert reopened.project.layers == session.project.layers
    assert layer.asset_ref in reopened.assets
    assert reopened.is_dirty is False
    assert reopened.can_undo is False
    assert reopened.can_redo is False
