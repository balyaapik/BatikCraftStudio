"""Regression tests for brush alpha and tile-background separation."""

from __future__ import annotations

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
from batikcraft_studio.imaging.artwork_viewport_renderer import ArtworkViewportRenderer
from batikcraft_studio.imaging.safe_viewport_renderer import project_visual_fingerprint
from batikcraft_studio.imaging.stroke_object import render_cropped_stroke


def _project(*, background: str, layers: list[Layer] | None = None) -> Project:
    return Project(
        metadata=ProjectMetadata(title="Brush alpha", creator="Test"),
        canvas=CanvasSpec(width=256, height=256, background_color=background),
        layers=layers or [],
    )


def test_empty_artwork_tile_is_transparent_not_project_background() -> None:
    project = _project(background="#8B5A2B")
    renderer = ArtworkViewportRenderer()
    tile = renderer.render_tile(
        project,
        {},
        project_fingerprint=project_visual_fingerprint(project, {}),
        zoom_scale=1.0,
        tile_x=0,
        tile_y=0,
    )

    assert tile.size == (256, 256)
    assert tile.getbbox() is None
    assert tile.getpixel((128, 128)) == (0, 0, 0, 0)


def test_real_brush_stroke_does_not_become_solid_bounding_box() -> None:
    cropped = render_cropped_stroke(
        canvas_width=256,
        canvas_height=256,
        points=[(48.0, 48.0), (128.0, 128.0), (208.0, 208.0)],
        brush_size=18,
        color="#8B5A2B",
        opacity=1.0,
        hardness=0.75,
        smoothing=0.25,
    )
    asset_ref = "assets/brush-alpha.png"
    stroke = LayerObject(
        name="Brush stroke",
        kind=ObjectKind.PAINT_STROKE,
        asset_ref=asset_ref,
        transform=Transform(x=cropped.center[0], y=cropped.center[1]),
        bounds=ObjectBounds(cropped.width, cropped.height),
        properties={
            "source_format": "PAINT_STROKE",
            "brush_color": "#8B5A2B",
            "brush_size": 18.0,
        },
    )
    layer = Layer(
        name="Active layer",
        kind=LayerKind.BATIKIFIED_OBJECT,
        node_kind=LayerNodeKind.LAYER,
        properties={"object_container": True},
        objects=(stroke,),
    )
    assets = {asset_ref: cropped.content}
    project = _project(background="#F7F2E8", layers=[layer])
    renderer = ArtworkViewportRenderer()
    tile = renderer.render_tile(
        project,
        assets,
        project_fingerprint=project_visual_fingerprint(project, assets),
        zoom_scale=1.0,
        tile_x=0,
        tile_y=0,
    )

    alpha = tile.getchannel("A")
    assert alpha.getbbox() is not None
    assert tile.getpixel((0, 0))[3] == 0
    assert tile.getpixel((255, 255))[3] == 0
    assert tile.getpixel((128, 128))[3] > 0

    opaque_or_partial = sum(1 for value in alpha.getdata() if value > 0)
    assert opaque_or_partial < tile.width * tile.height // 4

    # Final presentation: transparent artwork is composited over one canvas
    # background, so no brush-colored rectangle can appear around the stroke.
    from PIL import Image

    presented = Image.new("RGBA", tile.size, (247, 242, 232, 255))
    presented.alpha_composite(tile)
    assert presented.getpixel((0, 0)) == (247, 242, 232, 255)
    center = presented.getpixel((128, 128))
    assert center[:3] != (247, 242, 232)
