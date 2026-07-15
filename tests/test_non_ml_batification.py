"""Tests for two-object Batification without an ML model."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from batikcraft_studio.application.non_ml_batification_session import (
    NonMLBatificationProjectSession,
)
from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Transform,
)
from batikcraft_studio.imaging.non_ml_batification import (
    NonMLBatificationMode,
    NonMLBatificationOptions,
    batify_with_motif,
    extract_motif_palette,
)


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _silhouette() -> Image.Image:
    image = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 8, 83, 87), fill=(185, 185, 185, 255))
    draw.ellipse((34, 30, 61, 59), fill=(235, 235, 235, 255))
    return image


def _line_source() -> Image.Image:
    image = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.line((8, 16, 88, 80), fill=(40, 40, 40, 255), width=5)
    return image


def _motif() -> Image.Image:
    image = Image.new("RGBA", (24, 24), (231, 194, 113, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 11, 11), fill=(78, 42, 30, 255))
    draw.rectangle((12, 12, 23, 23), fill=(78, 42, 30, 255))
    draw.ellipse((7, 7, 17, 17), outline=(170, 69, 55, 255), width=3)
    return image


def test_fill_outline_clips_real_motif_to_source_silhouette() -> None:
    result = batify_with_motif(_png(_silhouette()), _png(_motif()))
    image = Image.open(BytesIO(result.content)).convert("RGBA")

    assert image.getpixel((0, 0))[3] == 0
    assert image.getpixel((48, 48))[3] > 0
    assert len(set(image.convert("RGB").getdata())) > 3
    assert result.palette
    assert result.darkest_color == result.palette[0]
    assert not result.line_like_source


def test_line_source_stays_a_line_instead_of_becoming_a_rectangle() -> None:
    options = NonMLBatificationOptions(mode=NonMLBatificationMode.FILL_OUTLINE)
    result = batify_with_motif(_png(_line_source()), _png(_motif()), options)
    image = Image.open(BytesIO(result.content)).convert("RGBA")
    alpha = image.getchannel("A")

    assert result.line_like_source
    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getpixel((48, 48)) > 0
    painted = sum(1 for value in alpha.getdata() if value > 0)
    assert painted < image.width * image.height // 5


def test_outline_mode_does_not_fill_silhouette_center() -> None:
    result = batify_with_motif(
        _png(_silhouette()),
        _png(_motif()),
        NonMLBatificationOptions(
            mode=NonMLBatificationMode.OUTLINE,
            outline_width=2,
        ),
    )
    image = Image.open(BytesIO(result.content)).convert("RGBA")

    assert image.getpixel((48, 48))[3] == 0
    assert image.getpixel((12, 48))[3] > 0


def test_palette_is_stable_and_ordered_dark_to_light() -> None:
    first = extract_motif_palette(_motif())
    second = extract_motif_palette(_motif())

    assert first == second
    assert first[0] == "#4E2A1E"
    assert "#E7C271" in first


def test_session_creates_result_in_source_layer_as_one_undo_step() -> None:
    session = NonMLBatificationProjectSession()
    project = session.new_project(
        title="Non-ML Batification",
        creator="Test",
        width=256,
        height=256,
    )
    layer = Layer(
        name="Objects",
        kind=LayerKind.BATIKIFIED_OBJECT,
        node_kind=LayerNodeKind.LAYER,
        properties={"object_container": True},
    )
    project.add_layer(layer)

    source_ref = "assets/source.png"
    motif_ref = "assets/motif.png"
    session._assets[source_ref] = _png(_silhouette())
    session._assets[motif_ref] = _png(_motif())
    source = LayerObject(
        name="Random object",
        kind=ObjectKind.RASTER,
        asset_ref=source_ref,
        transform=Transform(x=100, y=100),
        bounds=ObjectBounds(96, 96),
    )
    motif = LayerObject(
        name="Batik motif",
        kind=ObjectKind.MOTIF,
        asset_ref=motif_ref,
        transform=Transform(x=200, y=100),
        bounds=ObjectBounds(24, 24),
    )
    project.add_object(layer.layer_id, source, select=False)
    project.add_object(layer.layer_id, motif, select=False)
    session.set_selected_objects([source.object_id, motif.object_id])

    result = session.batify_selected_with_motif()

    refreshed = project.get_layer(layer.layer_id)
    assert len(refreshed.objects) == 3
    assert project.object_layer_id(result.object_id) == layer.layer_id
    assert not project.get_object(source.object_id).visible
    assert project.get_object(motif.object_id).visible
    assert result.properties["batification_source_object_id"] == source.object_id
    assert result.properties["batification_motif_object_id"] == motif.object_id
    assert session.selected_object_ids == (result.object_id,)

    assert session.undo()
    assert len(session.require_project().get_layer(layer.layer_id).objects) == 2
    assert session.require_project().get_object(source.object_id).visible

    assert session.redo()
    restored = session.require_project().get_layer(layer.layer_id)
    assert len(restored.objects) == 3
    assert not session.require_project().get_object(source.object_id).visible
