from __future__ import annotations

from io import BytesIO

from PIL import Image

from batikcraft_studio.domain import (
    CanvasSpec,
    Layer,
    LayerKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Project,
    Transform,
)
from batikcraft_studio.imaging.artwork_viewport_renderer import ArtworkViewportRenderer
from batikcraft_studio.imaging.safe_viewport_renderer import project_visual_fingerprint
from batikcraft_studio.ui.inkscape_renderer_compat import (
    install_inkscape_renderer_compat,
)


def _asset_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGBA", (16, 16), (190, 40, 50, 255)).save(output, format="PNG")
    return output.getvalue()


def _project() -> tuple[Project, LayerObject, LayerObject, dict[str, bytes]]:
    first = LayerObject(
        name="Pertama",
        kind=ObjectKind.RASTER,
        asset_ref="asset.png",
        transform=Transform(x=100, y=100),
        bounds=ObjectBounds(16, 16),
    )
    second = LayerObject(
        name="Kedua",
        kind=ObjectKind.RASTER,
        asset_ref="asset.png",
        transform=Transform(x=700, y=100),
        bounds=ObjectBounds(16, 16),
    )
    project = Project.create(
        "Renderer compatibility",
        "BatikCraft",
        canvas=CanvasSpec(width=1024, height=256, background_color="#FFFFFF"),
    )
    project.add_layer(
        Layer(
            name="Objek",
            kind=LayerKind.RASTER,
            objects=(first, second),
        )
    )
    return project, first, second, {"asset.png": _asset_bytes()}


def test_artwork_renderer_can_hide_and_restore_dragged_objects() -> None:
    install_inkscape_renderer_compat()
    project, first, second, assets = _project()
    renderer = ArtworkViewportRenderer()
    fingerprint = project_visual_fingerprint(project, assets)

    normal = renderer.render_tile(
        project,
        assets,
        project_fingerprint=fingerprint,
        zoom_scale=1.0,
        tile_x=0,
        tile_y=0,
    )
    assert normal.getpixel((100, 100))[3] > 0

    renderer.set_interaction_exclusions((first.object_id,))
    renderer.invalidate_project_bounds((90, 90, 110, 110))
    filtered = renderer.render_tile(
        project,
        assets,
        project_fingerprint=fingerprint,
        zoom_scale=1.0,
        tile_x=0,
        tile_y=0,
    )
    assert filtered.getpixel((100, 100))[3] == 0

    renderer.set_interaction_exclusions(())
    renderer.invalidate_project_bounds((90, 90, 110, 110))
    restored = renderer.render_tile(
        project,
        assets,
        project_fingerprint=fingerprint,
        zoom_scale=1.0,
        tile_x=0,
        tile_y=0,
    )
    assert restored.getpixel((100, 100))[3] > 0
    assert project.get_object(second.object_id) == second


def test_bounded_move_reuses_unaffected_screen_tile() -> None:
    install_inkscape_renderer_compat()
    project, first, _second, assets = _project()
    renderer = ArtworkViewportRenderer()
    before_fingerprint = project_visual_fingerprint(project, assets)

    old_dirty_tile = renderer.render_tile(
        project,
        assets,
        project_fingerprint=before_fingerprint,
        zoom_scale=1.0,
        tile_x=0,
        tile_y=0,
    )
    unaffected_before = renderer.render_tile(
        project,
        assets,
        project_fingerprint=before_fingerprint,
        zoom_scale=1.0,
        tile_x=1,
        tile_y=0,
    )

    project.update_object(
        first.object_id,
        transform=Transform(x=140, y=100),
    )
    renderer.invalidate_project_bounds((90, 90, 110, 110))
    renderer.invalidate_project_bounds((130, 90, 150, 110))
    after_fingerprint = project_visual_fingerprint(project, assets)

    unaffected_after = renderer.render_tile(
        project,
        assets,
        project_fingerprint=after_fingerprint,
        zoom_scale=1.0,
        tile_x=1,
        tile_y=0,
    )
    dirty_after = renderer.render_tile(
        project,
        assets,
        project_fingerprint=after_fingerprint,
        zoom_scale=1.0,
        tile_x=0,
        tile_y=0,
    )

    assert unaffected_after is unaffected_before
    assert dirty_after is not old_dirty_tile
    assert dirty_after.getpixel((140, 100))[3] > 0
