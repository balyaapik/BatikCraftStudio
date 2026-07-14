from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.imaging import (
    EditableBatikAsset,
    encode_batik_asset,
    humanize_raster_asset,
    load_batik_asset,
)


def _transparent_motif() -> bytes:
    image = Image.new("RGBA", (128, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((14, 10, 114, 86), outline=(83, 40, 24, 255), width=8)
    draw.line((30, 48, 98, 48), fill=(139, 90, 43, 255), width=5)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_batikasset_round_trip_preserves_source_and_metadata() -> None:
    source = _transparent_motif()
    asset = EditableBatikAsset(
        name="Kawung Buatan Saya",
        category="motif-pokok",
        content=source,
        width=128,
        height=96,
        metadata={"daerah": "Eksperimen", "catatan": "Editable"},
    )

    encoded = encode_batik_asset(asset)
    decoded = load_batik_asset(encoded, filename="kawung.batikasset")

    assert decoded.name == asset.name
    assert decoded.category == "motif-pokok"
    assert decoded.content == source
    assert dict(decoded.metadata) == dict(asset.metadata)


def test_humanize_is_seeded_repeatable_and_preserves_dimensions() -> None:
    source = _transparent_motif()
    first = humanize_raster_asset(
        source,
        seed=42,
        edge_wobble=0.2,
        ink_breaks=0.1,
        opacity_variation=0.15,
    )
    second = humanize_raster_asset(
        source,
        seed=42,
        edge_wobble=0.2,
        ink_breaks=0.1,
        opacity_variation=0.15,
    )

    assert first == second
    assert first != source
    with Image.open(BytesIO(first)) as image:
        assert image.size == (128, 96)
        assert image.mode == "RGBA"


def test_session_humanize_keeps_source_and_can_reset() -> None:
    session = ProjectSession()
    session.new_project(title="Humanize", creator="Perajin", width=400, height=300)
    layer = session.create_object_layer("Pustaka")
    item = session.import_batik_asset(
        "motif.png",
        _transparent_motif(),
        target_layer_id=layer.layer_id,
        default_category="motif-pokok",
    )
    source_ref = item.asset_ref
    assert source_ref is not None
    source_bytes = session.assets[source_ref]

    changed = session.humanize_object(
        item.object_id,
        seed=7,
        edge_wobble=0.2,
        ink_breaks=0.08,
        opacity_variation=0.1,
    )
    assert changed.asset_ref != source_ref
    assert changed.properties["source_asset_ref"] == source_ref
    assert session.assets[source_ref] == source_bytes

    restored = session.reset_object_humanize(item.object_id)
    assert restored.asset_ref == source_ref
    assert restored.properties["humanized"] is False
    assert session.assets[source_ref] == source_bytes
