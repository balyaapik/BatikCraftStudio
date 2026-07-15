"""Regression tests for the critical M4J hotfix."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from batikcraft_studio.application.hotfix_session import _fill_enclosed_png_complete
from batikcraft_studio.application.hotfix_session_v2 import FinalHotfixProjectSession
from batikcraft_studio.domain import (
    CanvasSpec,
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Project,
    ProjectMetadata,
    Transform,
)
from batikcraft_studio.imaging.gradient import apply_gradient_to_image
from batikcraft_studio.imaging.safe_viewport_renderer import (
    SCREEN_TILE_SIZE,
    SafeViewportRenderer,
    project_visual_fingerprint,
    screen_tile_geometry,
    visible_screen_tile_coords,
)


def _png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _closed_ring(*, gap: bool = False) -> Image.Image:
    image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((5, 5, 34, 34), outline=(20, 20, 20, 255), width=3)
    if gap:
        draw.rectangle((19, 4, 20, 8), fill=(0, 0, 0, 0))
    return image


def test_screen_tiles_remain_physically_bounded_at_800_percent() -> None:
    bounds, output = screen_tile_geometry(2000, 2000, 8.0, 0, 0)
    assert output == (SCREEN_TILE_SIZE, SCREEN_TILE_SIZE)
    assert bounds == (0.0, 0.0, 64.0, 64.0)

    tiles = visible_screen_tile_coords(
        0,
        0,
        1000,
        700,
        2000,
        2000,
        8.0,
        overscan=1,
    )
    assert tiles
    assert max(x for x, _y in tiles) <= 2
    assert max(y for _x, y in tiles) <= 2


def test_edge_screen_tile_is_cropped_not_oversized() -> None:
    _bounds, output = screen_tile_geometry(100, 100, 1.0, 0, 0)
    assert output == (100, 100)


def test_safe_renderer_never_allocates_a_zoom_scaled_tile() -> None:
    project = Project(
        metadata=ProjectMetadata(title="Tile", creator="Test"),
        canvas=CanvasSpec(width=2000, height=2000, background_color="#FFFFFF"),
        layers=[],
    )
    renderer = SafeViewportRenderer()
    fingerprint = project_visual_fingerprint(project, {})
    tile = renderer.render_tile(
        project,
        {},
        project_fingerprint=fingerprint,
        zoom_scale=8.0,
        tile_x=0,
        tile_y=0,
    )
    assert tile.size == (512, 512)
    assert renderer.debug_stats()["max_tile_dimension"] <= 512


def test_gradient_stop_alpha_multiplies_source_alpha() -> None:
    source = Image.new("RGBA", (32, 32), (255, 255, 255, 200))
    result = apply_gradient_to_image(
        source,
        {
            "start_color": "#FF0000",
            "end_color": "#0000FF",
            "start_opacity": 0.0,
            "end_opacity": 1.0,
            "angle": 0.0,
        },
        "linear_gradient",
    )
    assert result.getpixel((16, 0))[3] < 30
    assert result.getpixel((16, 31))[3] > 170
    assert result.getpixel((16, 31))[3] <= 200


def test_complete_fill_has_no_hole_or_exterior_leak() -> None:
    filled = Image.open(BytesIO(_fill_enclosed_png_complete(_png_bytes(_closed_ring()), "#CC6633")))
    alpha = filled.convert("RGBA").getchannel("A")
    assert alpha.getpixel((20, 20)) >= 250
    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getpixel((8, 20)) > 0


def test_small_accidental_gap_is_closed_in_project_space() -> None:
    filled = Image.open(
        BytesIO(_fill_enclosed_png_complete(_png_bytes(_closed_ring(gap=True)), "#336699"))
    )
    assert filled.convert("RGBA").getpixel((20, 20))[3] >= 240


def test_public_session_routes_brush_to_active_generic_layer() -> None:
    session = FinalHotfixProjectSession()
    project = session.new_project(title="Routing", creator="Test", width=100, height=100)
    layer = Layer(
        name="Chosen Layer",
        kind=LayerKind.BATIKIFIED_OBJECT,
        node_kind=LayerNodeKind.LAYER,
        properties={"object_container": True},
    )
    project.add_layer(layer)

    target = session.ensure_active_paint_layer()
    assert target.layer_id == layer.layer_id
    session.apply_paint_stroke(
        target.layer_id,
        points=[(10, 10), (20, 20), (30, 20)],
        brush_size=4,
        color="#221100",
    )

    assert len(project.layers) == 1
    assert len(project.get_layer(layer.layer_id).objects) == 1
    stroke = project.get_layer(layer.layer_id).objects[0]
    assert project.object_layer_id(stroke.object_id) == layer.layer_id


def test_reapplying_fill_reuses_object_id_in_source_layer() -> None:
    session = FinalHotfixProjectSession()
    project = session.new_project(title="Fill", creator="Test", width=100, height=100)
    layer = Layer(
        name="Fill Layer",
        kind=LayerKind.BATIKIFIED_OBJECT,
        node_kind=LayerNodeKind.LAYER,
        properties={"object_container": True},
    )
    project.add_layer(layer)
    source_ref = "assets/ring.png"
    session._assets[source_ref] = _png_bytes(_closed_ring())
    stroke = LayerObject(
        name="Closed Stroke",
        kind=ObjectKind.PAINT_STROKE,
        asset_ref=source_ref,
        transform=Transform(x=50, y=50),
        bounds=ObjectBounds(40, 40),
        properties={"source_format": "PAINT_STROKE"},
    )
    project.add_object(layer.layer_id, stroke, select=True)

    first_fill, _source = session.fill_closed_object(stroke.object_id, "#AA3300")
    second_fill, _source = session.fill_closed_object(stroke.object_id, "#0033AA")

    assert first_fill.object_id == second_fill.object_id
    assert project.object_layer_id(second_fill.object_id) == layer.layer_id
    assert len(project.get_layer(layer.layer_id).objects) == 2
    objects = project.get_layer(layer.layer_id).objects
    fill_index = next(i for i, item in enumerate(objects) if item.object_id == second_fill.object_id)
    stroke_index = next(i for i, item in enumerate(objects) if item.object_id == stroke.object_id)
    assert fill_index + 1 == stroke_index
