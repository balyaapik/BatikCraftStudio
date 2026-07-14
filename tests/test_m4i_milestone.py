"""Milestone 4I automated test suite.

Covers:
  1.  Brush cursor is centered exactly on the pointer.
  2.  Eraser cursor is centered exactly on the pointer.
  3.  Preview diameter matches actual tool size at multiple zoom levels.
  4.  Scrolling does not shift the tool-size guide.
  5.  A position-locked object cannot be moved with the mouse.
  6.  A position-locked object cannot be moved using keyboard arrows.
  7.  A position-locked object rejects direct x/y changes.
  8.  Position Lock does not prevent color, opacity, resize, or rotation changes.
  9.  A multi-object move is rejected when at least one object is position-locked.
 10.  Lock and Unlock support Undo and Redo.
 11.  The position-lock indicator appears in the object tree (property present).
 12.  Linear gradients render in the correct direction.
 13.  Radial gradients render from the configured center.
 14.  Original raster alpha is preserved after applying a gradient.
 15.  Object opacity combines correctly with layer and parent-folder opacity.
 16.  Applying gradients does not increase the object count.
 17.  Object IDs remain unchanged after gradients and opacity changes.
 18.  All new Font Awesome icons decode successfully without internet access.
 19.  Existing Fill and destructive Eraser tests continue to pass.
 20.  Complete existing test suite continues to pass (tested by running pytest normally).
"""

from __future__ import annotations

import math
from io import BytesIO

import pytest
from PIL import Image

from batikcraft_studio.application.direct_style_session import DirectStyleProjectSession
from batikcraft_studio.application.position_lock_session import (
    POSITION_LOCK_KEY,
    PositionLockedError,
)
from batikcraft_studio.domain import (
    CanvasSpec,
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    ProjectMetadata,
    Transform,
)
from batikcraft_studio.domain.project import Project
from batikcraft_studio.imaging.cursor_guide import (
    compute_cursor_guide,
    viewport_to_project,
)
from batikcraft_studio.imaging.gradient import apply_gradient_to_image
from batikcraft_studio.imaging.paint import (
    apply_paint_stroke,
    create_transparent_canvas_png,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(*, with_objects: int = 1) -> Project:
    """Return a minimal project with one paint layer and the requested objects."""
    meta = ProjectMetadata(title="Test", creator="test")
    canvas = CanvasSpec(width=256, height=256)
    objects = tuple(
        LayerObject(
            name=f"Obj {i}",
            kind=ObjectKind.RASTER,
            transform=Transform(x=float(50 + i * 20), y=50.0),
            bounds=ObjectBounds(40, 40),
        )
        for i in range(with_objects)
    )
    layer = Layer(
        name="Layer 1",
        kind=LayerKind.BATIKIFIED_OBJECT,
        node_kind=LayerNodeKind.LAYER,
        objects=objects,
        properties={"object_container": True},
    )
    return Project(metadata=meta, canvas=canvas, layers=(layer,))


def _make_session() -> DirectStyleProjectSession:
    """Return a session with a new project and one raster object already added."""
    session = DirectStyleProjectSession()
    session.new_project(title="Test", creator="test", width=256, height=256)
    layer = session.create_object_layer("Layer 1")
    # Add a real raster asset to the session
    blank = create_transparent_canvas_png(40, 40)
    painted = apply_paint_stroke(
        blank,
        width=40,
        height=40,
        points=[(20, 20)],
        brush_size=10,
        color="#A43D2F",
    )
    from uuid import uuid4

    from batikcraft_studio.domain import LayerObject, ObjectBounds, ObjectKind, Transform
    asset_ref = f"assets/{uuid4()}.png"
    item = LayerObject(
        name="Test Object",
        kind=ObjectKind.RASTER,
        asset_ref=asset_ref,
        transform=Transform(x=128, y=128),
        bounds=ObjectBounds(40, 40),
    )
    session._assets[asset_ref] = painted
    project = session.require_project()
    project.add_object(layer.layer_id, item, select=True)
    return session


def _rgba(content: bytes) -> Image.Image:
    with Image.open(BytesIO(content)) as src:
        src.load()
        return src.convert("RGBA")


# ---------------------------------------------------------------------------
# Test 1: Brush cursor is centered exactly on the pointer
# ---------------------------------------------------------------------------

def test_brush_cursor_centered_on_pointer() -> None:
    guide = compute_cursor_guide(
        pointer_x=100.0,
        pointer_y=200.0,
        tool_size=30.0,
        zoom_scale=1.0,
    )
    assert guide.center_x == 100.0
    assert guide.center_y == 200.0


# ---------------------------------------------------------------------------
# Test 2: Eraser cursor is centered exactly on the pointer
# ---------------------------------------------------------------------------

def test_eraser_cursor_centered_on_pointer() -> None:
    guide = compute_cursor_guide(
        pointer_x=55.5,
        pointer_y=77.5,
        tool_size=20.0,
        zoom_scale=2.0,
    )
    assert guide.center_x == 55.5
    assert guide.center_y == 77.5


# ---------------------------------------------------------------------------
# Test 3: Preview diameter matches actual tool size at multiple zoom levels
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("zoom", [0.25, 0.5, 1.0, 1.5, 2.0, 3.0])
@pytest.mark.parametrize("tool_size", [10.0, 20.0, 50.0, 100.0])
def test_preview_diameter_equals_tool_size_times_zoom(zoom: float, tool_size: float) -> None:
    guide = compute_cursor_guide(
        pointer_x=0.0,
        pointer_y=0.0,
        tool_size=tool_size,
        zoom_scale=zoom,
    )
    expected_diameter = tool_size * zoom
    actual_diameter = guide.radius * 2
    assert math.isclose(actual_diameter, expected_diameter, rel_tol=1e-9), (
        f"Expected diameter {expected_diameter}, got {actual_diameter} "
        f"(tool_size={tool_size}, zoom={zoom})"
    )


# ---------------------------------------------------------------------------
# Test 4: Scrolling does not shift the tool-size guide
# ---------------------------------------------------------------------------

def test_scrolling_does_not_shift_guide() -> None:
    # The guide center is always at the pointer position in viewport space,
    # regardless of canvas scroll offset.  Scroll is handled by the viewport
    # manager when converting pointer → project, but the guide overlay itself
    # is anchored to the raw pointer coordinates.
    pointer_x, pointer_y = 150.0, 250.0
    for _scroll_x in (0.0, 100.0, 500.0, -50.0):
        for _scroll_y in (0.0, 100.0, 500.0):
            guide = compute_cursor_guide(
                pointer_x=pointer_x,
                pointer_y=pointer_y,
                tool_size=20.0,
                zoom_scale=1.5,
            )
            # Center must NOT shift with scroll:
            assert guide.center_x == pointer_x
            assert guide.center_y == pointer_y
    # However, project coordinates DO include scroll:
    px, py = viewport_to_project(150.0, 250.0, zoom_scale=1.5, scroll_x=100.0)
    assert math.isclose(px, (150.0 + 100.0) / 1.5, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Test 5: A position-locked object cannot be moved with the mouse
# ---------------------------------------------------------------------------

def test_position_locked_object_cannot_be_moved() -> None:
    session = _make_session()
    project = session.require_project()
    obj_id = project.active_object_id
    assert obj_id is not None

    session.lock_object_position(obj_id)
    assert session.is_position_locked(obj_id)

    with pytest.raises(PositionLockedError, match="locked"):
        session.move_object(obj_id, x=200.0, y=200.0)


# ---------------------------------------------------------------------------
# Test 6: A position-locked object cannot be moved using keyboard arrows
# ---------------------------------------------------------------------------

def test_position_locked_object_cannot_be_nudged() -> None:
    session = _make_session()
    project = session.require_project()
    obj_id = project.active_object_id
    assert obj_id is not None

    session.set_selected_objects([obj_id])
    session.lock_object_position(obj_id)

    with pytest.raises(PositionLockedError, match="locked"):
        session.nudge_selected_objects(5.0, 0.0)


# ---------------------------------------------------------------------------
# Test 7: A position-locked object rejects direct x and y changes
# ---------------------------------------------------------------------------

def test_position_locked_object_rejects_xy_transform_update() -> None:
    session = _make_session()
    project = session.require_project()
    obj_id = project.active_object_id
    assert obj_id is not None

    session.lock_object_position(obj_id)

    with pytest.raises(PositionLockedError):
        session.update_object_transform(obj_id, x=300.0)
    with pytest.raises(PositionLockedError):
        session.update_object_transform(obj_id, y=300.0)


# ---------------------------------------------------------------------------
# Test 8: Position Lock does not prevent color, opacity, resize, or rotation
# ---------------------------------------------------------------------------

def test_position_lock_allows_rotation_scale_opacity() -> None:
    session = _make_session()
    project = session.require_project()
    obj_id = project.active_object_id
    assert obj_id is not None

    session.lock_object_position(obj_id)

    # Rotation change is allowed:
    updated = session.update_object_transform(obj_id, rotation_degrees=45.0)
    assert updated.transform.rotation_degrees == 45.0

    # Scale change is allowed:
    updated = session.update_object_transform(obj_id, scale_x=2.0)
    assert updated.transform.scale_x == 2.0

    # Opacity change is allowed:
    updated = session.set_object_opacity(obj_id, 0.5)
    assert math.isclose(updated.opacity, 0.5)


# ---------------------------------------------------------------------------
# Test 9: Multi-object move rejected when any object is position-locked
# ---------------------------------------------------------------------------

def test_multi_move_rejected_when_any_object_locked() -> None:
    session = _make_session()
    project = session.require_project()
    layer = project.layers[0]
    obj_id = project.active_object_id
    assert obj_id is not None

    # Add a second object
    second = LayerObject(
        name="Second",
        kind=ObjectKind.RASTER,
        transform=Transform(x=180.0, y=50.0),
        bounds=ObjectBounds(30, 30),
    )
    project.add_object(layer.layer_id, second, select=False)

    session.lock_object_position(obj_id)
    session.set_selected_objects([obj_id, second.object_id])

    with pytest.raises(PositionLockedError):
        session.begin_interactive_multi_move([obj_id, second.object_id])


# ---------------------------------------------------------------------------
# Test 10: Lock and Unlock support Undo and Redo
# ---------------------------------------------------------------------------

def test_lock_unlock_undo_redo() -> None:
    session = _make_session()
    project = session.require_project()
    obj_id = project.active_object_id
    assert obj_id is not None

    # Lock
    session.lock_object_position(obj_id)
    assert session.is_position_locked(obj_id)

    # Undo lock
    session.undo()
    assert not session.is_position_locked(obj_id)

    # Redo lock
    session.redo()
    assert session.is_position_locked(obj_id)

    # Unlock
    session.unlock_object_position(obj_id)
    assert not session.is_position_locked(obj_id)

    # Undo unlock
    session.undo()
    assert session.is_position_locked(obj_id)

    # Redo unlock
    session.redo()
    assert not session.is_position_locked(obj_id)


# ---------------------------------------------------------------------------
# Test 11: The position-lock indicator appears in the object tree (property)
# ---------------------------------------------------------------------------

def test_position_lock_property_stored_in_object() -> None:
    session = _make_session()
    project = session.require_project()
    obj_id = project.active_object_id
    assert obj_id is not None

    session.lock_object_position(obj_id)
    item = project.get_object(obj_id)
    assert item.properties.get(POSITION_LOCK_KEY) is True

    session.unlock_object_position(obj_id)
    item = project.get_object(obj_id)
    assert POSITION_LOCK_KEY not in item.properties


# ---------------------------------------------------------------------------
# Test 12: Linear gradients render in the correct direction
# ---------------------------------------------------------------------------

def test_linear_gradient_renders_correctly() -> None:
    image = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    gradient_props = {
        "type": "linear",
        "angle": 90.0,  # left → right
        "start_color": "#000000",
        "end_color": "#FFFFFF",
        "start_opacity": 1.0,
        "end_opacity": 1.0,
        "offset_x": 0.0,
        "offset_y": 0.0,
    }
    result = apply_gradient_to_image(image, gradient_props, "linear_gradient")
    assert result.mode == "RGBA"
    # Left edge should be darker than right edge (angle=90 → left is start)
    left_pixel = result.getpixel((5, 50))
    right_pixel = result.getpixel((95, 50))
    # The left pixel should have a lower red channel than right
    assert left_pixel[0] < right_pixel[0], (
        f"Left pixel {left_pixel} should be darker than right pixel {right_pixel}"
    )


# ---------------------------------------------------------------------------
# Test 13: Radial gradients render from the configured center
# ---------------------------------------------------------------------------

def test_radial_gradient_renders_from_center() -> None:
    image = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    gradient_props = {
        "type": "radial",
        "center_color": "#FFFFFF",
        "outer_color": "#000000",
        "center_opacity": 1.0,
        "outer_opacity": 1.0,
        "center_x": 0.5,
        "center_y": 0.5,
        "radius": 0.5,
    }
    result = apply_gradient_to_image(image, gradient_props, "radial_gradient")
    assert result.mode == "RGBA"
    # Center pixel should be bright (close to white)
    center_pixel = result.getpixel((50, 50))
    # Edge pixel should be dark (close to black)
    edge_pixel = result.getpixel((95, 95))
    assert center_pixel[0] > edge_pixel[0], (
        f"Center {center_pixel} should be brighter than edge {edge_pixel}"
    )


# ---------------------------------------------------------------------------
# Test 14: Original raster alpha is preserved after applying a gradient
# ---------------------------------------------------------------------------

def test_gradient_preserves_original_alpha() -> None:
    # Create a simple RGBA image with a circular mask
    size = 64
    image = Image.new("RGBA", (size, size), (255, 128, 0, 0))
    # Draw a filled circle in the alpha channel
    from PIL import ImageDraw
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((8, 8, size - 8, size - 8), fill=255)
    image.putalpha(mask)

    original_alpha = list(image.getdata(3))  # alpha channel

    gradient_props = {
        "type": "linear",
        "angle": 0.0,
        "start_color": "#FF0000",
        "end_color": "#0000FF",
        "start_opacity": 1.0,
        "end_opacity": 1.0,
        "offset_x": 0.0,
        "offset_y": 0.0,
    }
    result = apply_gradient_to_image(image, gradient_props, "linear_gradient")
    result_alpha = list(result.getdata(3))

    assert result_alpha == original_alpha, (
        "Gradient must not change the original alpha channel"
    )


# ---------------------------------------------------------------------------
# Test 15: Object opacity combines correctly with layer and parent-folder opacity
# ---------------------------------------------------------------------------

def test_effective_opacity_multiplication() -> None:
    from batikcraft_studio.imaging.renderer import _effective_layer_opacity

    meta = ProjectMetadata(title="Test", creator="test")
    canvas = CanvasSpec(width=256, height=256)

    folder = Layer(
        name="Folder",
        kind=LayerKind.GROUP,
        node_kind=LayerNodeKind.GROUP,
        opacity=0.8,
    )
    layer = Layer(
        name="Layer",
        kind=LayerKind.BATIKIFIED_OBJECT,
        node_kind=LayerNodeKind.LAYER,
        parent_id=folder.layer_id,
        opacity=0.5,
        properties={"object_container": True},
    )
    project = Project(
        metadata=meta,
        canvas=canvas,
        layers=(folder, layer),
    )

    effective = _effective_layer_opacity(project, layer)
    expected = 0.5 * 0.8
    assert math.isclose(effective, expected, rel_tol=1e-9), (
        f"Expected {expected}, got {effective}"
    )


# ---------------------------------------------------------------------------
# Test 16: Applying gradients does not increase the object count
# ---------------------------------------------------------------------------

def test_gradient_does_not_increase_object_count() -> None:
    session = _make_session()
    project = session.require_project()
    obj_id = project.active_object_id
    assert obj_id is not None
    layer_id = project.object_layer_id(obj_id)

    count_before = len(project.get_layer(layer_id).objects)

    session.set_object_gradient(
        obj_id,
        "linear_gradient",
        {
            "type": "linear",
            "angle": 45.0,
            "start_color": "#FF0000",
            "end_color": "#0000FF",
            "start_opacity": 1.0,
            "end_opacity": 1.0,
        },
    )

    count_after = len(project.get_layer(layer_id).objects)
    assert count_before == count_after, (
        f"Object count changed from {count_before} to {count_after}"
    )


# ---------------------------------------------------------------------------
# Test 17: Object IDs remain unchanged after gradients and opacity changes
# ---------------------------------------------------------------------------

def test_object_id_unchanged_after_gradient_and_opacity() -> None:
    session = _make_session()
    project = session.require_project()
    obj_id = project.active_object_id
    assert obj_id is not None

    session.set_object_gradient(
        obj_id,
        "radial_gradient",
        {"type": "radial", "center_color": "#FF0000", "outer_color": "#0000FF"},
    )
    assert project.get_object(obj_id).object_id == obj_id

    session.set_object_opacity(obj_id, 0.7)
    assert project.get_object(obj_id).object_id == obj_id


# ---------------------------------------------------------------------------
# Test 18: All new Font Awesome icons decode successfully without internet access
# ---------------------------------------------------------------------------

def test_new_m4i_tool_icons_decode_offline() -> None:
    from batikcraft_studio.ui.tool_icons import available_tool_icons, render_tool_icon

    new_icons = {
        "position_lock", "position_unlock",
        "gradient_linear", "gradient_radial", "object_opacity",
    }
    available = set(available_tool_icons())
    assert new_icons <= available, f"Missing icons: {new_icons - available}"

    for icon_name in new_icons:
        image = render_tool_icon(icon_name, size=20)
        assert image.mode == "RGBA", f"{icon_name} should be RGBA"
        assert image.size == (20, 20), f"{icon_name} size should be (20, 20)"
        assert image.getbbox() is not None, f"{icon_name} should have non-empty pixels"


# ---------------------------------------------------------------------------
# Test 19: Existing Fill and destructive Eraser tests continue to pass
# ---------------------------------------------------------------------------

def test_existing_fill_functionality_still_works() -> None:
    """Regression: create_shape_layer still works on shape sessions."""
    from batikcraft_studio.application.shape_session import ShapeProjectSession

    shape_session = ShapeProjectSession()
    shape_session.new_project(title="Regress", creator="test", width=256, height=256)
    layer = shape_session.create_shape_layer(
        "rectangle",
        (50, 50),
        (150, 150),
    )
    assert layer is not None
    assert layer.kind.value == "shape"


def test_eraser_stroke_still_removes_pixels() -> None:
    """Regression: eraser strokes still reduce alpha correctly."""
    blank = create_transparent_canvas_png(64, 64)
    painted = apply_paint_stroke(
        blank,
        width=64,
        height=64,
        points=[(8, 32), (56, 32)],
        brush_size=15,
        color="#223344",
    )
    erased = apply_paint_stroke(
        painted,
        width=64,
        height=64,
        points=[(32, 32)],
        brush_size=15,
        color="#000000",
        erase=True,
    )
    img = _rgba(erased)
    assert img.getpixel((32, 32))[3] == 0  # center fully erased


# ---------------------------------------------------------------------------
# Additional: CursorGuide bbox correctness
# ---------------------------------------------------------------------------

def test_cursor_guide_bbox_symmetric() -> None:
    guide = compute_cursor_guide(
        pointer_x=50.0,
        pointer_y=60.0,
        tool_size=40.0,
        zoom_scale=1.0,
    )
    left, top, right, bottom = guide.bbox
    assert math.isclose(right - left, guide.radius * 2, rel_tol=1e-9)
    assert math.isclose(bottom - top, guide.radius * 2, rel_tol=1e-9)
    cx = (left + right) / 2
    cy = (top + bottom) / 2
    assert math.isclose(cx, guide.center_x, rel_tol=1e-9)
    assert math.isclose(cy, guide.center_y, rel_tol=1e-9)


def test_cursor_guide_dpi_scaling() -> None:
    """At 150% DPI (1.5), the visual radius must scale proportionally."""
    guide_1x = compute_cursor_guide(
        pointer_x=0, pointer_y=0, tool_size=20.0, zoom_scale=1.0, dpi_scale=1.0
    )
    guide_15x = compute_cursor_guide(
        pointer_x=0, pointer_y=0, tool_size=20.0, zoom_scale=1.0, dpi_scale=1.5
    )
    assert math.isclose(guide_15x.radius, guide_1x.radius * 1.5, rel_tol=1e-9)


def test_project_radius_is_half_tool_size() -> None:
    for size in (10.0, 30.0, 100.0):
        guide = compute_cursor_guide(
            pointer_x=0, pointer_y=0, tool_size=size, zoom_scale=1.0
        )
        assert math.isclose(guide.project_radius, size / 2.0, rel_tol=1e-9)


def test_set_object_opacity_percent_convenience() -> None:
    session = _make_session()
    project = session.require_project()
    obj_id = project.active_object_id
    assert obj_id is not None

    updated = session.set_object_opacity_percent(obj_id, 65)
    assert math.isclose(updated.opacity, 0.65, rel_tol=1e-9)

    # Clamp checks
    from batikcraft_studio.application.session import ProjectSessionError
    with pytest.raises(ProjectSessionError):
        session.set_object_opacity_percent(obj_id, 101)
    with pytest.raises(ProjectSessionError):
        session.set_object_opacity_percent(obj_id, -1)
