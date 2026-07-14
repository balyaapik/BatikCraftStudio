from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from batikcraft_studio.application import (
    GROUP_ID_KEY,
    GROUP_NAME_KEY,
    MultiObjectProjectSession,
)


def _asset(label: str) -> bytes:
    image = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((5, 5, 43, 43), outline=(80, 40, 25, 255), width=5)
    draw.text((17, 14), label, fill=(80, 40, 25, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _session(tmp_path: Path):
    session = MultiObjectProjectSession(tmp_path / "models")
    session.new_project(
        title="Multi Object",
        creator="Tester",
        width=400,
        height=300,
    )
    first = session.import_raster_object("first.png", _asset("A"))
    second = session.import_raster_object("second.png", _asset("B"))
    third = session.import_raster_object("third.png", _asset("C"))
    project = session.require_project()
    first = project.update_object(
        first.object_id,
        transform=replace(first.transform, x=80, y=80),
    )
    second = project.update_object(
        second.object_id,
        transform=replace(second.transform, x=150, y=80),
    )
    third = project.update_object(
        third.object_id,
        transform=replace(third.transform, x=300, y=220),
    )
    return session, first, second, third


def test_rectangle_and_shift_toggle_select_multiple_objects(tmp_path: Path) -> None:
    session, first, second, third = _session(tmp_path)

    selected = session.select_objects_in_rectangle((40, 40, 190, 120))

    assert {item.object_id for item in selected} == {
        first.object_id,
        second.object_id,
    }
    session.select_object_for_editing(third.object_id, toggle=True)
    assert session.selected_object_ids == (
        first.object_id,
        second.object_id,
        third.object_id,
    )
    session.select_object_for_editing(first.object_id, toggle=True)
    assert session.selected_object_ids == (second.object_id, third.object_id)


def test_group_selection_persists_and_clicking_one_member_selects_group(
    tmp_path: Path,
) -> None:
    session, first, second, _third = _session(tmp_path)
    session.set_selected_objects([first.object_id, second.object_id])

    group_id = session.group_selected_objects("Tokoh Utama")
    project = session.require_project()

    assert project.get_object(first.object_id).properties[GROUP_ID_KEY] == group_id
    assert project.get_object(second.object_id).properties[GROUP_ID_KEY] == group_id
    assert project.get_object(first.object_id).properties[GROUP_NAME_KEY] == "Tokoh Utama"

    path = tmp_path / "grouped.batikcraft"
    session.save_as(path)
    reopened = MultiObjectProjectSession(tmp_path / "models-reopened")
    reopened.open_project(path)

    selected = reopened.select_object_for_editing(first.object_id)
    assert {item.object_id for item in selected} == {
        first.object_id,
        second.object_id,
    }


def test_ungroup_is_one_undoable_mutation(tmp_path: Path) -> None:
    session, first, second, _third = _session(tmp_path)
    session.set_selected_objects([first.object_id, second.object_id])
    group_id = session.group_selected_objects()

    removed = session.ungroup_selected_objects()
    project = session.require_project()

    assert removed == (group_id,)
    assert GROUP_ID_KEY not in project.get_object(first.object_id).properties
    assert GROUP_ID_KEY not in project.get_object(second.object_id).properties

    assert session.undo() is True
    restored = session.require_project()
    assert restored.get_object(first.object_id).properties[GROUP_ID_KEY] == group_id
    assert restored.get_object(second.object_id).properties[GROUP_ID_KEY] == group_id


def test_multi_move_commits_once_and_undo_restores_every_object(tmp_path: Path) -> None:
    session, first, second, _third = _session(tmp_path)
    session.set_selected_objects([first.object_id, second.object_id])

    session.begin_interactive_multi_move()
    session.preview_interactive_multi_move(35, -20)
    assert session.commit_interactive_multi_move() is True

    moved = session.require_project()
    assert moved.get_object(first.object_id).transform.x == 115
    assert moved.get_object(first.object_id).transform.y == 60
    assert moved.get_object(second.object_id).transform.x == 185
    assert moved.get_object(second.object_id).transform.y == 60

    assert session.undo() is True
    restored = session.require_project()
    assert restored.get_object(first.object_id).transform.x == 80
    assert restored.get_object(first.object_id).transform.y == 80
    assert restored.get_object(second.object_id).transform.x == 150
    assert restored.get_object(second.object_id).transform.y == 80


def test_pasting_one_group_member_does_not_join_the_original_group(tmp_path: Path) -> None:
    session, first, second, _third = _session(tmp_path)
    session.set_selected_objects([first.object_id, second.object_id])
    session.group_selected_objects()

    session.copy_object(first.object_id)
    pasted = session.paste_object()

    assert GROUP_ID_KEY not in pasted.properties
    assert GROUP_NAME_KEY not in pasted.properties
