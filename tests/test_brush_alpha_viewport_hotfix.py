"""Regression tests for brush/line alpha and viewport background separation."""

from __future__ import annotations

from typing import Any

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
from batikcraft_studio.imaging.shape import build_shape_geometry
from batikcraft_studio.imaging.stroke_object import render_cropped_stroke
from batikcraft_studio.ui.context_tool_editor_hotfix_v3 import (
    ContextToolEditorWorkspaceView,
)


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

    from PIL import Image

    presented = Image.new("RGBA", tile.size, (247, 242, 232, 255))
    presented.alpha_composite(tile)
    assert presented.getpixel((0, 0)) == (247, 242, 232, 255)
    center = presented.getpixel((128, 128))
    assert center[:3] != (247, 242, 232)


def test_line_shape_renders_as_a_line_not_a_brown_rectangle() -> None:
    geometry = build_shape_geometry(
        "line",
        (24.0, 32.0),
        (220.0, 188.0),
        stroke_color="#8B5A2B",
        fill_color="#8B5A2B",
        stroke_width=8.0,
        stroke_enabled=True,
        fill_enabled=True,
    )
    properties = dict(geometry.properties)
    line = LayerObject(
        name="Brown line",
        kind=ObjectKind.SHAPE,
        transform=Transform(x=geometry.center_x, y=geometry.center_y),
        bounds=ObjectBounds(
            float(properties["pixel_width"]),
            float(properties["pixel_height"]),
        ),
        properties=properties,
    )
    layer = Layer(
        name="Line layer",
        kind=LayerKind.BATIKIFIED_OBJECT,
        node_kind=LayerNodeKind.LAYER,
        properties={"object_container": True},
        objects=(line,),
    )
    project = _project(background="#F7F2E8", layers=[layer])
    renderer = ArtworkViewportRenderer()
    tile = renderer.render_tile(
        project,
        {},
        project_fingerprint=project_visual_fingerprint(project, {}),
        zoom_scale=1.0,
        tile_x=0,
        tile_y=0,
    )

    alpha = tile.getchannel("A")
    assert alpha.getbbox() is not None
    assert tile.getpixel((0, 0))[3] == 0
    assert tile.getpixel((255, 255))[3] == 0
    assert tile.getpixel((122, 110))[3] > 0
    painted = sum(1 for value in alpha.getdata() if value > 0)
    assert painted < tile.width * tile.height // 8


class _FakeCanvas:
    def __init__(self) -> None:
        self.next_id = 1
        self.items: dict[int, dict[str, Any]] = {}
        self.raise_calls: list[tuple[Any, Any]] = []

    def create_rectangle(self, *coords: float, **options: Any) -> int:
        item_id = self.next_id
        self.next_id += 1
        self.items[item_id] = {
            "type": "rectangle",
            "coords": coords,
            "fill": options.get("fill"),
            "tags": set(options.get("tags", ())),
        }
        return item_id

    def type(self, item_id: int) -> str:
        item = self.items.get(item_id)
        return "" if item is None else str(item["type"])

    def coords(self, item_id: int, *coords: float) -> None:
        self.items[item_id]["coords"] = coords

    def itemconfigure(self, item_id: int, **options: Any) -> None:
        self.items[item_id].update(options)

    def find_withtag(self, tag: str) -> tuple[int, ...]:
        return tuple(
            item_id
            for item_id, item in self.items.items()
            if tag in item["tags"]
        )

    def tag_raise(self, item: Any, above: Any) -> None:
        self.raise_calls.append((item, above))

    def delete(self, selector: int | str) -> None:
        if isinstance(selector, int):
            self.items.pop(selector, None)
            return
        for item_id in self.find_withtag(selector):
            self.items.pop(item_id, None)


class _BackgroundHost:
    _draw_project_background = ContextToolEditorWorkspaceView._draw_project_background
    _canvas_item_exists = ContextToolEditorWorkspaceView._canvas_item_exists

    def __init__(self) -> None:
        self.canvas = _FakeCanvas()
        self._preview_left = 10.0
        self._preview_top = 20.0
        self._project_background_id: int | None = None


def test_project_background_is_not_deleted_with_canvas_chrome() -> None:
    host = _BackgroundHost()
    project = _project(background="#F7F2E8")

    host._draw_project_background(project, 1.0)
    background_id = host._project_background_id
    assert background_id is not None
    assert host.canvas.items[background_id]["tags"] == {"project-background"}

    host.canvas.delete("canvas-chrome")
    assert host.canvas.type(background_id) == "rectangle"

    host.canvas.create_rectangle(0, 0, 1, 1, tags=("canvas-shadow",))
    host._draw_project_background(project, 1.0)
    assert host._project_background_id == background_id
    assert (background_id, "canvas-shadow") in host.canvas.raise_calls
    assert ("project-tile", background_id) in host.canvas.raise_calls


def test_deleted_background_id_is_recreated_instead_of_exposing_shadow() -> None:
    host = _BackgroundHost()
    project = _project(background="#FFFFFF")

    host._draw_project_background(project, 1.0)
    deleted_id = host._project_background_id
    assert deleted_id is not None
    host.canvas.delete(deleted_id)

    host._draw_project_background(project, 1.0)
    assert host._project_background_id is not None
    assert host._project_background_id != deleted_id
    assert host.canvas.type(host._project_background_id) == "rectangle"
