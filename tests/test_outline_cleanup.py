from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from batikcraft_studio.application import OutlineCleanupProjectSession, ProjectSessionError
from batikcraft_studio.imaging.outline_cleanup import (
    OutlineCleanupOptions,
    clean_outline,
)


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _alpha(content: bytes) -> Image.Image:
    with Image.open(BytesIO(content)) as opened:
        opened.load()
        return opened.convert("RGBA").getchannel("A")


def _noisy_transparent_outline() -> bytes:
    image = Image.new("RGBA", (96, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((12, 10, 82, 68), radius=14, outline=(0, 0, 0, 255), width=6)
    draw.point((2, 2), fill=(0, 0, 0, 255))
    draw.rectangle((90, 74, 91, 75), fill=(0, 0, 0, 255))
    return _png(image)


def test_cleanup_removes_small_speckles_and_keeps_main_line() -> None:
    result = clean_outline(
        _noisy_transparent_outline(),
        OutlineCleanupOptions(
            threshold=64,
            speckle_area=8,
            smooth_radius=0,
            close_gaps=0,
            source_mode="alpha",
        ),
    )

    alpha = _alpha(result.content)
    assert result.removed_components == 2
    assert result.removed_pixels == 5
    assert alpha.getpixel((2, 2)) == 0
    assert alpha.getpixel((12, 24)) == 255
    assert result.output_coverage > 0.05


def test_cleanup_smoothing_creates_antialiased_edges() -> None:
    result = clean_outline(
        _noisy_transparent_outline(),
        OutlineCleanupOptions(
            threshold=64,
            speckle_area=8,
            smooth_radius=1.2,
            close_gaps=0,
            source_mode="alpha",
        ),
    )

    histogram = _alpha(result.content).histogram()
    assert sum(histogram[1:255]) > 0


def test_outline_only_turns_solid_region_into_hollow_contour() -> None:
    image = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((15, 15, 64, 64), fill=(0, 0, 0, 255))

    result = clean_outline(
        _png(image),
        OutlineCleanupOptions(
            threshold=64,
            speckle_area=0,
            smooth_radius=0,
            close_gaps=1,
            outline_only=True,
            source_mode="alpha",
        ),
    )

    alpha = _alpha(result.content)
    assert alpha.getpixel((15, 40)) > 0
    assert alpha.getpixel((40, 40)) == 0


def test_dark_mode_removes_opaque_white_background() -> None:
    image = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
    ImageDraw.Draw(image).line((8, 32, 56, 32), fill=(20, 20, 20, 255), width=5)

    result = clean_outline(
        _png(image),
        OutlineCleanupOptions(
            threshold=80,
            speckle_area=0,
            smooth_radius=0,
            close_gaps=0,
            source_mode="dark",
        ),
    )

    alpha = _alpha(result.content)
    assert alpha.getpixel((2, 2)) == 0
    assert alpha.getpixel((32, 32)) == 255
    assert result.resolved_source_mode == "dark"


def test_preview_does_not_mutate_and_apply_is_one_undo_step() -> None:
    session = OutlineCleanupProjectSession()
    session.new_project(title="Outline", creator="Test", width=400, height=300)
    item = session.import_external_image("noisy.png", _noisy_transparent_outline())
    project = session.require_project()
    original = project.get_object(item.object_id)
    original_layer = project.object_layer_id(item.object_id)
    original_revision = project.revision

    plan = session.prepare_outline_cleanup()
    preview = session.render_outline_cleanup_preview(
        plan,
        OutlineCleanupOptions(
            threshold=64,
            speckle_area=8,
            smooth_radius=0.5,
            close_gaps=0,
            source_mode="alpha",
        ),
    )

    assert project.revision == original_revision
    assert project.get_object(item.object_id) == original

    updated = session.commit_outline_cleanup_preview(plan, preview)

    assert updated.object_id == original.object_id
    assert updated.transform == original.transform
    assert project.object_layer_id(updated.object_id) == original_layer
    assert updated.asset_ref != original.asset_ref
    assert updated.properties["outline_cleanup_removed_components"] == 2

    session.undo()
    restored = session.require_project().get_object(item.object_id)
    assert restored.asset_ref == original.asset_ref
    assert restored.transform == original.transform

    session.redo()
    redone = session.require_project().get_object(item.object_id)
    assert redone.asset_ref == updated.asset_ref


def test_stale_outline_preview_is_rejected() -> None:
    session = OutlineCleanupProjectSession()
    session.new_project(title="Outline", creator="Test", width=400, height=300)
    session.import_external_image("noisy.png", _noisy_transparent_outline())
    plan = session.prepare_outline_cleanup()
    preview = session.render_outline_cleanup_preview(plan)
    session.import_external_image("other.png", _noisy_transparent_outline())

    with pytest.raises(ProjectSessionError, match="Project berubah"):
        session.commit_outline_cleanup_preview(plan, preview)
