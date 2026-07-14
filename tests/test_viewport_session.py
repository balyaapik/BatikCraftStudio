from __future__ import annotations

from pathlib import Path

from batikcraft_studio.application import ViewportProjectSession
from batikcraft_studio.ui.viewport_editor import choose_grid_step


def _session(tmp_path: Path) -> ViewportProjectSession:
    session = ViewportProjectSession(tmp_path / "models")
    session.new_project(title="Viewport", creator="Tester", width=800, height=600)
    return session


def test_copy_paste_multi_selection_preserves_relative_position_and_remaps_group(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    first = session.create_shape_layer("rectangle", (80, 90), (180, 190))
    second = session.create_shape_layer("ellipse", (240, 130), (340, 230))
    session.set_selected_objects([first.object_id, second.object_id])
    source_group = session.group_selected_objects("Komposisi")

    copied = session.copy_selected_objects()
    pasted = session.paste_selected_objects()

    assert len(copied) == 2
    assert len(pasted) == 2
    assert session.require_project().object_count == 4
    assert pasted[1].transform.x - pasted[0].transform.x == (
        second.transform.x - first.transform.x
    )
    assert pasted[1].transform.y - pasted[0].transform.y == (
        second.transform.y - first.transform.y
    )
    pasted_groups = {
        item.properties.get("object_group_id")
        for item in pasted
    }
    assert len(pasted_groups) == 1
    assert source_group not in pasted_groups
    assert session.selected_object_ids == tuple(item.object_id for item in pasted)


def test_cut_is_one_undoable_deletion_and_clipboard_remains_available(tmp_path: Path) -> None:
    session = _session(tmp_path)
    first = session.create_shape_layer("rectangle", (40, 40), (140, 140))
    second = session.create_shape_layer("polygon", (180, 40), (300, 160))
    session.set_selected_objects([first.object_id, second.object_id])

    cut = session.cut_selected_objects()

    assert len(cut) == 2
    assert session.require_project().object_count == 0
    assert session.has_multi_object_clipboard is True
    assert session.undo() is True
    assert session.require_project().object_count == 2
    assert session.redo() is True
    assert session.require_project().object_count == 0

    pasted = session.paste_selected_objects()
    assert len(pasted) == 2
    assert session.require_project().object_count == 2


def test_delete_selected_objects_is_one_undo_step(tmp_path: Path) -> None:
    session = _session(tmp_path)
    objects = (
        session.create_shape_layer("rectangle", (20, 20), (100, 100)),
        session.create_shape_layer("ellipse", (120, 20), (200, 100)),
        session.create_shape_layer("polygon", (220, 20), (320, 120)),
    )
    session.set_selected_objects([item.object_id for item in objects])

    removed = session.delete_selected_objects()

    assert len(removed) == 3
    assert session.require_project().object_count == 0
    assert session.undo() is True
    assert session.require_project().object_count == 3


def test_pasted_objects_persist_after_save_and_reopen(tmp_path: Path) -> None:
    session = _session(tmp_path)
    first = session.create_shape_layer("rectangle", (100, 100), (220, 200))
    second = session.create_shape_layer("ellipse", (260, 100), (380, 200))
    session.set_selected_objects([first.object_id, second.object_id])
    session.copy_selected_objects()
    pasted = session.paste_selected_objects()
    destination = tmp_path / "viewport.batikcraft"
    session.save_as(destination)

    reopened = ViewportProjectSession(tmp_path / "models-reopened")
    reopened.open_project(destination)

    assert reopened.require_project().object_count == 4
    for item in pasted:
        assert reopened.require_project().get_object(item.object_id).name.endswith("salinan")


def test_grid_interval_stays_readable_across_zoom_levels() -> None:
    assert choose_grid_step(1.0) == 25.0
    assert choose_grid_step(0.2) == 100.0
    assert choose_grid_step(2.0) == 25.0
    assert choose_grid_step(0.0) == 25.0
