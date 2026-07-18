from __future__ import annotations

import pytest

from batikcraft_studio.application import MultiObjectProjectSession, ProjectSessionError
from batikcraft_studio.domain import (
    Layer,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Transform,
)
from batikcraft_studio.ui.canvas_selection_semantics import (
    _visible_canvas_object_ids,
    install_canvas_selection_semantics,
)
from batikcraft_studio.ui.inkscape_canvas_patch import install_inkscape_canvas_patch
from batikcraft_studio.ui.inkscape_pointer_hotpath import install_inkscape_pointer_hotpath

install_inkscape_canvas_patch()
install_inkscape_pointer_hotpath()
install_canvas_selection_semantics()


def _object(
    name: str,
    x: float,
    *,
    locked: bool = False,
    visible: bool = True,
) -> LayerObject:
    return LayerObject(
        name=name,
        kind=ObjectKind.SHAPE,
        locked=locked,
        visible=visible,
        transform=Transform(x=x, y=50),
        bounds=ObjectBounds(20, 20),
        properties={"shape": "rectangle", "fill": "#4E2A1E"},
    )


def _session_with_lock_states() -> tuple[
    MultiObjectProjectSession,
    LayerObject,
    LayerObject,
    LayerObject,
    LayerObject,
]:
    session = MultiObjectProjectSession()
    project = session.new_project(
        title="Selection semantics",
        creator="Tests",
        width=400,
        height=300,
    )
    movable = _object("Movable", 40)
    locked = _object("Locked object", 90, locked=True)
    hidden = _object("Hidden", 140, visible=False)
    layer_locked = _object("Locked layer object", 190)
    project.add_layer(
        Layer(
            name="Regular layer",
            objects=(movable, locked, hidden),
        )
    )
    project.add_layer(
        Layer(
            name="Locked layer",
            locked=True,
            objects=(layer_locked,),
        )
    )
    return session, movable, locked, hidden, layer_locked


def test_ctrl_a_object_source_includes_visible_locked_objects() -> None:
    session, movable, locked, _hidden, layer_locked = _session_with_lock_states()

    assert _visible_canvas_object_ids(session.require_project()) == (
        movable.object_id,
        locked.object_id,
        layer_locked.object_id,
    )


def test_collective_move_skips_locked_members_and_commits_once() -> None:
    session, movable, locked, _hidden, layer_locked = _session_with_lock_states()
    project = session.require_project()
    session.set_selected_objects(
        [movable.object_id, locked.object_id, layer_locked.object_id],
        expand_groups=False,
    )
    revision_before = project.revision

    moving = session.begin_interactive_multi_move()
    assert tuple(item.object_id for item in moving) == (movable.object_id,)

    session.preview_interactive_multi_move(30, 15)
    assert project.get_object(movable.object_id).transform == movable.transform
    assert project.get_object(locked.object_id).transform == locked.transform
    assert project.get_object(layer_locked.object_id).transform == layer_locked.transform

    assert session.commit_interactive_multi_move() is True
    assert project.revision == revision_before + 1
    assert project.get_object(movable.object_id).transform.x == movable.transform.x + 30
    assert project.get_object(movable.object_id).transform.y == movable.transform.y + 15
    assert project.get_object(locked.object_id).transform == locked.transform
    assert project.get_object(layer_locked.object_id).transform == layer_locked.transform
    assert session.selected_object_ids == (
        movable.object_id,
        locked.object_id,
        layer_locked.object_id,
    )

    assert session.undo() is True
    restored = session.require_project()
    assert restored.get_object(movable.object_id).transform == movable.transform
    assert restored.get_object(locked.object_id).transform == locked.transform
    assert restored.get_object(layer_locked.object_id).transform == layer_locked.transform


def test_collective_move_rejects_selection_when_every_object_is_locked() -> None:
    session, _movable, locked, _hidden, layer_locked = _session_with_lock_states()
    session.set_selected_objects(
        [locked.object_id, layer_locked.object_id],
        expand_groups=False,
    )

    with pytest.raises(ProjectSessionError, match="terkunci"):
        session.begin_interactive_multi_move()
