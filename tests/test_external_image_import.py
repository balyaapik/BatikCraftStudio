"""Regression tests for external image insertion and the personal asset library."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from batikcraft_studio.application import ExternalImageProjectSession
from batikcraft_studio.assets import PERSONAL_PACK_ID, AssetLibrary, PersonalAssetStore
from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    ObjectNotFoundError,
)
from batikcraft_studio.imaging.raster import normalize_raster_image
from batikcraft_studio.ui.external_image_io import (
    paths_from_clipboard_text,
    paths_from_drop_data,
)
from PIL import Image, features


def _image_bytes(image_format: str, *, size: tuple[int, int] = (80, 60)) -> bytes:
    image = Image.new("RGBA", size, (128, 74, 42, 255))
    output = BytesIO()
    target = image.convert("RGB") if image_format in {"JPEG", "TIFF"} else image
    target.save(output, format=image_format)
    return output.getvalue()


@pytest.mark.parametrize(
    ("image_format", "expected"),
    (("JPEG", "JPEG"), ("TIFF", "TIFF")),
)
def test_normalize_external_raster_formats(image_format: str, expected: str) -> None:
    raster = normalize_raster_image(_image_bytes(image_format))

    assert raster.source_format == expected
    assert (raster.width, raster.height) == (80, 60)
    with Image.open(BytesIO(raster.content)) as normalized:
        assert normalized.format == "PNG"
        assert normalized.mode == "RGBA"


@pytest.mark.skipif(not features.check("webp"), reason="Pillow build has no WebP codec")
def test_normalize_webp_image() -> None:
    raster = normalize_raster_image(_image_bytes("WEBP"))
    assert raster.source_format == "WEBP"
    assert (raster.width, raster.height) == (80, 60)


def test_personal_asset_store_persists_thumbnail_and_deduplicates(tmp_path: Path) -> None:
    library = AssetLibrary(tmp_path / "library")
    store = PersonalAssetStore(library)
    content = _image_bytes("TIFF")

    first = store.import_image("motif bunga.tiff", content)
    second = store.import_image("salinan motif.tiff", content)

    assert first.key == second.key
    assert first.pack_id == PERSONAL_PACK_ID
    assert library.asset_count == 1
    assert first.width == 80
    assert first.height == 60
    assert first.metadata is not None
    assert first.metadata["source_format"] == "TIFF"
    assert library.read_thumbnail(first)
    with Image.open(BytesIO(library.read_asset(first))) as stored:
        assert stored.format == "PNG"
        assert stored.mode == "RGBA"

    reloaded = AssetLibrary(tmp_path / "library")
    assert reloaded.get_asset(first.key).name == "motif bunga"


def test_external_image_becomes_transformable_object_at_requested_position() -> None:
    session = ExternalImageProjectSession()
    project = session.new_project(
        title="External image",
        creator="Test",
        width=600,
        height=400,
    )
    layer = Layer(
        name="Imported",
        kind=LayerKind.BATIKIFIED_OBJECT,
        node_kind=LayerNodeKind.LAYER,
        properties={"object_container": True},
    )
    project.add_layer(layer)

    item = session.import_external_image(
        "cloth.webp",
        _image_bytes("PNG", size=(200, 100)),
        position=(145.0, 175.0),
        target_layer_id=layer.layer_id,
        library_key="user-imports:image-123",
    )

    assert item.transform.x == 145.0
    assert item.transform.y == 175.0
    assert item.bounds.width == 200
    assert item.bounds.height == 100
    assert item.properties["external_image_import"] is True
    assert item.properties["transformable"] is True
    assert item.properties["personal_library_key"] == "user-imports:image-123"
    assert project.object_layer_id(item.object_id) == layer.layer_id

    transformed = session.update_object_transform(
        item.object_id,
        x=220,
        y=210,
        rotation_degrees=32,
        scale_x=0.75,
        scale_y=1.25,
    )
    assert transformed.transform.x == 220
    assert transformed.transform.rotation_degrees == 32
    assert transformed.transform.scale_x == 0.75
    assert transformed.transform.scale_y == 1.25


def test_external_import_is_one_undoable_project_mutation() -> None:
    session = ExternalImageProjectSession()
    session.new_project(title="Undo", creator="Test", width=320, height=240)

    item = session.import_external_image("photo.jpg", _image_bytes("JPEG"))
    assert session.require_project().get_object(item.object_id)

    assert session.undo() is True
    with pytest.raises(ObjectNotFoundError):
        session.require_project().get_object(item.object_id)

    assert session.redo() is True
    assert session.require_project().get_object(item.object_id).visible is True


def test_drop_and_clipboard_path_parsing_support_spaces_and_file_uris(tmp_path: Path) -> None:
    first = tmp_path / "motif satu.tiff"
    second = tmp_path / "object.webp"
    ignored = tmp_path / "notes.txt"
    first.write_bytes(_image_bytes("TIFF"))
    second.write_bytes(_image_bytes("PNG"))
    ignored.write_text("not an image", encoding="utf-8")

    dropped = paths_from_drop_data(
        lambda _data: (str(first), str(second), str(ignored), str(first)),
        "unused",
    )
    assert dropped == (first, second)

    clipboard = paths_from_clipboard_text(
        f"# copied files\n{first.as_uri()}\n{second}\n{ignored}\n"
    )
    assert clipboard == (first, second)
