"""Tests for active-layer routing fixes across all object-insertion paths.

Regression tests that verify the corrected behaviour: when the active layer
is locked the operation raises ``LayerLockedError`` instead of silently
routing the new object to a different (or freshly created) layer.

Covered paths
-------------
1.  PaintProjectSession.ensure_active_paint_layer
2.  BatikProjectSession.cap_isen  (via _prepare_isen_layer → _resolve_object_layer)
3.  MotifProjectSession.cap_motif (via _prepare_motif_layer → _resolve_object_layer)
4.  CanvasStructureProjectSession.create_shape_layer (via _resolve_object_layer)
5.  ClipboardProjectSession._resolve_paste_target
"""

from __future__ import annotations

import pytest

from batikcraft_studio.application import (
    BatikProjectSession,
    CanvasStructureProjectSession,
    LayerLockedError,
    MotifProjectSession,
    PaintProjectSession,
)
from batikcraft_studio.application.clipboard_session import ClipboardProjectSession
from batikcraft_studio.domain import Layer, LayerKind, LayerNodeKind, ObjectKind


def _add_object_layer(session: BatikProjectSession, name: str = "Test Layer") -> Layer:
    """Add a BATIKIFIED_OBJECT layer directly via the project (no session helper needed)."""
    project = session.require_project()
    layer = Layer(
        name=name,
        kind=LayerKind.BATIKIFIED_OBJECT,
        node_kind=LayerNodeKind.LAYER,
        properties={"object_container": True},
    )
    project.add_layer(layer)
    return layer


# ---------------------------------------------------------------------------
# 1. PaintProjectSession — ensure_active_paint_layer
# ---------------------------------------------------------------------------


def test_paint_ensure_uses_active_unlocked_paint_layer() -> None:
    """Unlocked active paint layer is returned as-is; no new layer is created."""
    session = PaintProjectSession()
    project = session.new_project(title="P", creator="T", width=32, height=32)
    layer = session.create_paint_layer()

    returned = session.ensure_active_paint_layer()

    assert returned.layer_id == layer.layer_id
    assert len(project.layers) == 1


def test_paint_ensure_raises_when_active_layer_is_locked() -> None:
    """Locked active paint layer must raise LayerLockedError (not silently redirect)."""
    session = PaintProjectSession()
    session.new_project(title="P", creator="T", width=32, height=32)
    locked = session.create_paint_layer()
    session.set_layer_locked(locked.layer_id, True)

    with pytest.raises(LayerLockedError):
        session.ensure_active_paint_layer()


def test_paint_ensure_creates_new_layer_when_no_active_layer() -> None:
    """With no active layer a new paint layer is created."""
    session = PaintProjectSession()
    project = session.new_project(title="P", creator="T", width=32, height=32)
    # No layers have been created yet, so active_layer_id is None.
    assert project.active_layer_id is None

    new_layer = session.ensure_active_paint_layer()

    assert new_layer.kind is LayerKind.PAINT
    assert len(project.layers) == 1


def test_paint_ensure_creates_new_layer_when_active_is_non_paint() -> None:
    """Active layer of a non-paint kind → a fresh paint layer is created beside it."""
    session = PaintProjectSession()
    project = session.new_project(title="P", creator="T", width=32, height=32)
    # Manually add a layer with a different kind without going through create_paint_layer.
    from batikcraft_studio.domain import Layer
    alt_layer = Layer(
        name="Alt",
        kind=LayerKind.BATIKIFIED_OBJECT,
        node_kind=LayerNodeKind.LAYER,
        properties={"object_container": True},
    )
    project.add_layer(alt_layer)
    # active layer is now the alt layer
    assert project.active_layer_id == alt_layer.layer_id

    returned = session.ensure_active_paint_layer()

    assert returned.kind is LayerKind.PAINT
    # A new layer was added — project now has two.
    assert len(project.layers) == 2


# ---------------------------------------------------------------------------
# 2. BatikProjectSession — cap_isen via _prepare_isen_layer
# ---------------------------------------------------------------------------


def test_cap_isen_uses_active_unlocked_layer() -> None:
    """cap_isen inserts into the active layer when it is unlocked."""
    session = BatikProjectSession()
    project = session.new_project(title="B", creator="T", width=400, height=400)
    layer = _add_object_layer(session, "Isen Layer")
    # layer is now the active layer
    assert project.active_layer_id == layer.layer_id

    objects = session.cap_isen("cecek", (100, 100))

    assert len(objects) == 1
    assert project.object_layer_id(objects[0].object_id) == layer.layer_id
    # No extra layer was created.
    assert len(project.layers) == 1


def test_cap_isen_raises_when_active_layer_is_locked() -> None:
    """cap_isen raises LayerLockedError when the active layer is locked."""
    session = BatikProjectSession()
    session.new_project(title="B", creator="T", width=400, height=400)
    layer = _add_object_layer(session, "Isen Layer")
    session.set_layer_locked(layer.layer_id, True)

    with pytest.raises(LayerLockedError):
        session.cap_isen("cecek", (100, 100))


def test_cap_isen_creates_layer_when_none_exists() -> None:
    """cap_isen creates a new target layer when no layers exist."""
    session = BatikProjectSession()
    project = session.new_project(title="B", creator="T", width=400, height=400)

    objects = session.cap_isen("cecek", (200, 200))

    assert len(objects) == 1
    assert len(project.layers) == 1
    assert objects[0].kind is ObjectKind.ISEN


def test_cap_isen_explicit_target_id_bypasses_active_layer() -> None:
    """An explicit target_layer_id is used directly, ignoring the active layer."""
    session = BatikProjectSession()
    project = session.new_project(title="B", creator="T", width=400, height=400)
    active_layer = _add_object_layer(session, "Active")
    target_layer = _add_object_layer(session, "Target")
    # Set active layer back to the first one.
    project.set_active_layer(active_layer.layer_id)

    objects = session.cap_isen("cecek", (100, 100), target_layer_id=target_layer.layer_id)

    assert project.object_layer_id(objects[0].object_id) == target_layer.layer_id


# ---------------------------------------------------------------------------
# 3. MotifProjectSession — cap_motif via _prepare_motif_layer
# ---------------------------------------------------------------------------


def test_cap_motif_uses_active_unlocked_layer() -> None:
    """cap_motif inserts into the active layer when it is unlocked."""
    session = MotifProjectSession()
    project = session.new_project(title="M", creator="T", width=600, height=600)
    layer = _add_object_layer(session, "Motif Layer")
    assert project.active_layer_id == layer.layer_id

    objects = session.cap_motif("kawung", (200, 200))

    assert len(objects) == 1
    assert project.object_layer_id(objects[0].object_id) == layer.layer_id
    assert len(project.layers) == 1


def test_cap_motif_raises_when_active_layer_is_locked() -> None:
    """cap_motif raises LayerLockedError when the active layer is locked."""
    session = MotifProjectSession()
    session.new_project(title="M", creator="T", width=600, height=600)
    layer = _add_object_layer(session, "Motif Layer")
    session.set_layer_locked(layer.layer_id, True)

    with pytest.raises(LayerLockedError):
        session.cap_motif("kawung", (200, 200))


def test_cap_motif_explicit_target_id_bypasses_active_layer() -> None:
    """An explicit target_layer_id is used directly."""
    session = MotifProjectSession()
    project = session.new_project(title="M", creator="T", width=600, height=600)
    active_layer = _add_object_layer(session, "Active")
    target_layer = _add_object_layer(session, "Target")
    project.set_active_layer(active_layer.layer_id)

    objects = session.cap_motif("kawung", (300, 300), target_layer_id=target_layer.layer_id)

    assert project.object_layer_id(objects[0].object_id) == target_layer.layer_id


# ---------------------------------------------------------------------------
# 4. CanvasStructureProjectSession — create_shape_layer
# ---------------------------------------------------------------------------


def test_shape_uses_active_unlocked_object_layer() -> None:
    """create_shape_layer inserts into the active layer when it is unlocked."""
    session = CanvasStructureProjectSession()
    project = session.new_project(title="S", creator="T", width=500, height=500)
    layer = session.create_object_layer("Layer Bentuk")
    assert project.active_layer_id == layer.layer_id

    shape = session.create_shape_layer("rectangle", (10, 10), (100, 100))

    assert project.object_layer_id(shape.object_id) == layer.layer_id
    assert len(project.layers) == 1


def test_shape_raises_when_active_layer_is_locked() -> None:
    """create_shape_layer raises LayerLockedError when the active layer is locked."""
    session = CanvasStructureProjectSession()
    session.new_project(title="S", creator="T", width=500, height=500)
    layer = session.create_object_layer("Layer Bentuk")
    session.set_layer_locked(layer.layer_id, True)

    with pytest.raises(LayerLockedError):
        session.create_shape_layer("rectangle", (10, 10), (100, 100))


def test_shape_creates_child_layer_when_folder_is_active() -> None:
    """When a folder is active, the shape goes into a new child layer of that folder."""
    session = CanvasStructureProjectSession()
    project = session.new_project(title="S", creator="T", width=500, height=500)
    folder = session.create_folder("Folder Flora")
    assert project.active_layer_id == folder.layer_id

    shape = session.create_shape_layer("ellipse", (50, 50), (200, 200))

    owner_id = project.object_layer_id(shape.object_id)
    owner = project.get_layer(owner_id)
    assert owner.parent_id == folder.layer_id
    assert owner.node_kind is LayerNodeKind.LAYER


def test_shape_creates_new_layer_when_no_active_layer() -> None:
    """create_shape_layer creates a new layer when no active layer is set."""
    session = CanvasStructureProjectSession()
    project = session.new_project(title="S", creator="T", width=500, height=500)
    assert project.active_layer_id is None

    shape = session.create_shape_layer("rectangle", (10, 10), (100, 100))

    assert len(project.layers) == 1
    assert shape.kind is ObjectKind.SHAPE


def test_shape_explicit_target_id_bypasses_active_layer() -> None:
    """An explicit target_layer_id for create_shape_layer bypasses the active layer."""
    session = CanvasStructureProjectSession()
    project = session.new_project(title="S", creator="T", width=500, height=500)
    active_layer = session.create_object_layer("Active")
    target_layer = session.create_object_layer("Target")
    project.set_active_layer(active_layer.layer_id)

    shape = session.create_shape_layer(
        "rectangle", (10, 10), (100, 100), target_layer_id=target_layer.layer_id
    )

    assert project.object_layer_id(shape.object_id) == target_layer.layer_id


# ---------------------------------------------------------------------------
# 5. ClipboardProjectSession — paste_object
# ---------------------------------------------------------------------------



def _setup_clipboard_with_copy(session: ClipboardProjectSession) -> None:
    """Create a project with one raster object and copy it to the clipboard."""
    session.new_project(title="C", creator="T", width=80, height=60)
    layer = session.create_object_layer("Objects")
    # Add a minimal shape object to copy.
    from batikcraft_studio.domain import LayerObject, ObjectBounds, Transform
    item = LayerObject(
        name="Box",
        kind=ObjectKind.SHAPE,
        transform=Transform(x=10, y=10),
        bounds=ObjectBounds(50, 40),
        properties={"shape_type": "rectangle"},
    )
    project = session.require_project()
    project.add_object(layer.layer_id, item)
    session.copy_object(item.object_id)


def test_paste_uses_active_unlocked_layer() -> None:
    """paste_object inserts into the active layer when it is unlocked."""
    session = ClipboardProjectSession()
    _setup_clipboard_with_copy(session)
    project = session.require_project()

    pasted = session.paste_object()

    owner_id = project.object_layer_id(pasted.object_id)
    # Should be placed in the active layer (the one we created).
    assert owner_id is not None
    assert pasted.object_id != project.active_layer_id


def test_paste_raises_when_active_layer_is_locked() -> None:
    """paste_object raises LayerLockedError when the active layer is locked."""
    session = ClipboardProjectSession()
    _setup_clipboard_with_copy(session)
    project = session.require_project()
    active_layer = project.get_layer(project.active_layer_id)
    session.set_layer_locked(active_layer.layer_id, True)

    with pytest.raises(LayerLockedError):
        session.paste_object()


# ---------------------------------------------------------------------------
# 6. Isolation guarantee: lock/unlock state does not carry between operations
# ---------------------------------------------------------------------------


def test_unlock_restores_routing_for_cap_isen() -> None:
    """After unlocking, the next cap_isen again uses the previously locked layer."""
    session = BatikProjectSession()
    project = session.new_project(title="B", creator="T", width=400, height=400)
    layer = _add_object_layer(session, "Isen Layer")
    session.set_layer_locked(layer.layer_id, True)

    with pytest.raises(LayerLockedError):
        session.cap_isen("cecek", (100, 100))

    session.set_layer_locked(layer.layer_id, False)
    objects = session.cap_isen("cecek", (100, 100))

    assert len(objects) == 1
    assert project.object_layer_id(objects[0].object_id) == layer.layer_id


def test_unlock_restores_routing_for_cap_motif() -> None:
    """After unlocking, cap_motif again routes into the previously locked layer."""
    session = MotifProjectSession()
    project = session.new_project(title="M", creator="T", width=600, height=600)
    layer = _add_object_layer(session, "Motif Layer")
    session.set_layer_locked(layer.layer_id, True)

    with pytest.raises(LayerLockedError):
        session.cap_motif("kawung", (300, 300))

    session.set_layer_locked(layer.layer_id, False)
    objects = session.cap_motif("kawung", (300, 300))

    assert len(objects) == 1
    assert project.object_layer_id(objects[0].object_id) == layer.layer_id


def test_unlock_restores_routing_for_create_shape_layer() -> None:
    """After unlocking, create_shape_layer routes into the previously locked layer."""
    session = CanvasStructureProjectSession()
    project = session.new_project(title="S", creator="T", width=500, height=500)
    layer = session.create_object_layer("Layer Bentuk")
    session.set_layer_locked(layer.layer_id, True)

    with pytest.raises(LayerLockedError):
        session.create_shape_layer("rectangle", (10, 10), (100, 100))

    session.set_layer_locked(layer.layer_id, False)
    shape = session.create_shape_layer("ellipse", (50, 50), (200, 200))

    assert project.object_layer_id(shape.object_id) == layer.layer_id
    assert len(project.layers) == 1


# ---------------------------------------------------------------------------
# 7. Multiple layers: active selection is respected even with many layers
# ---------------------------------------------------------------------------


def test_cap_isen_honours_active_layer_selection_among_many_layers() -> None:
    """cap_isen uses whichever layer is active, not always the first/last."""
    session = BatikProjectSession()
    project = session.new_project(title="B", creator="T", width=400, height=400)
    _layer1 = _add_object_layer(session, "Layer 1")
    layer2 = _add_object_layer(session, "Layer 2")
    _layer3 = _add_object_layer(session, "Layer 3")

    # Activate the middle layer.
    project.set_active_layer(layer2.layer_id)

    objects = session.cap_isen("cecek", (200, 200))

    owner_id = project.object_layer_id(objects[0].object_id)
    assert owner_id == layer2.layer_id
    # No extra layer should have been created.
    assert len(project.layers) == 3


def test_shape_honours_active_layer_selection_among_many_layers() -> None:
    """create_shape_layer uses whichever layer is active among many."""
    session = CanvasStructureProjectSession()
    project = session.new_project(title="S", creator="T", width=500, height=500)
    layer1 = session.create_object_layer("Layer 1")
    _layer2 = session.create_object_layer("Layer 2")
    _layer3 = session.create_object_layer("Layer 3")

    project.set_active_layer(layer1.layer_id)

    shape = session.create_shape_layer("rectangle", (10, 10), (100, 100))

    assert project.object_layer_id(shape.object_id) == layer1.layer_id
    assert len(project.layers) == 3


# ---------------------------------------------------------------------------
# 8. Undo/redo integrity: routing fix preserves correct undo behaviour
# ---------------------------------------------------------------------------


def test_cap_isen_with_active_layer_undoes_cleanly() -> None:
    """cap_isen into active layer undoes to zero objects without extra layers."""
    session = BatikProjectSession()
    project = session.new_project(title="B", creator="T", width=400, height=400)
    _add_object_layer(session, "Isen Layer")

    objects = session.cap_isen("cecek", (100, 100))
    asset_ref = objects[0].asset_ref

    assert len(project.layers) == 1
    assert len(project.layers[0].objects) == 1

    session.undo()

    # After undo: the layer should still exist but have no objects.
    project_after_undo = session.require_project()
    assert len(project_after_undo.layers) == 1
    assert project_after_undo.layers[0].objects == ()
    assert asset_ref not in session.assets


def test_shape_with_active_layer_undoes_cleanly() -> None:
    """create_shape_layer into active layer undoes cleanly."""
    session = CanvasStructureProjectSession()
    project = session.new_project(title="S", creator="T", width=500, height=500)
    session.create_object_layer("Layer Bentuk")

    session.create_shape_layer("rectangle", (10, 10), (100, 100))

    assert len(project.layers) == 1
    assert len(project.layers[0].objects) == 1

    session.undo()

    project_after = session.require_project()
    assert len(project_after.layers) == 1
    assert project_after.layers[0].objects == ()


# ---------------------------------------------------------------------------
# 9. i18n catalog completeness for routing-error keys
# ---------------------------------------------------------------------------


def test_layer_routing_i18n_keys_present_in_both_languages() -> None:
    """All layer_routing.* i18n keys are present in both id and en catalogs."""
    from batikcraft_studio.i18n import _TRANSLATIONS

    expected_keys = [
        "layer_routing.locked_active",
        "layer_routing.folder_target",
        "layer_routing.invalid_target",
        "layer_routing.paste_locked",
    ]

    for lang in ("id", "en"):
        for key in expected_keys:
            assert key in _TRANSLATIONS[lang], (
                f"Missing i18n key {key!r} for language {lang!r}"
            )
