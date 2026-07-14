from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from batikcraft_studio.application import ProjectSession, ProjectSessionError
from batikcraft_studio.ui.keyboard import (
    ISEN_TOOL_SEQUENCE,
    OBJECT_COPY_SEQUENCE,
    OBJECT_PASTE_SEQUENCE,
    SELECT_TOOL_SEQUENCE,
)


def _asset_png() -> bytes:
    image = Image.new("RGBA", (72, 48), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((5, 4, 67, 44), fill=(102, 51, 25, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_copy_paste_creates_independent_object_and_assets() -> None:
    session = ProjectSession()
    project = session.new_project(title="Clipboard", creator="Perajin", width=400, height=300)
    layer = session.create_object_layer("Motif")
    source = session.import_batik_asset(
        "motif.png",
        _asset_png(),
        target_layer_id=layer.layer_id,
        default_category="motif-pokok",
    )
    session.move_object(source.object_id, x=120, y=90)

    copied = session.copy_object()
    pasted = session.paste_object()

    assert copied.object_id == source.object_id
    assert pasted.object_id != source.object_id
    assert pasted.name == f"{source.name} salinan"
    assert pasted.transform.x == 144
    assert pasted.transform.y == 114
    assert pasted.bounds == source.bounds
    assert pasted.kind == source.kind
    assert pasted.asset_ref != source.asset_ref
    assert pasted.asset_ref is not None
    assert source.asset_ref is not None
    assert session.assets[pasted.asset_ref] == session.assets[source.asset_ref]
    assert project.active_object_id == pasted.object_id
    assert len(project.get_layer(layer.layer_id).objects) == 2

    assert session.undo() is True
    restored = session.require_project()
    assert len(restored.get_layer(layer.layer_id).objects) == 1
    assert pasted.asset_ref not in session.assets


def test_repeated_paste_uses_progressive_offset_from_copied_source() -> None:
    session = ProjectSession()
    session.new_project(title="Offsets", creator="Perajin", width=400, height=300)
    layer = session.create_object_layer("Motif")
    source = session.import_batik_asset(
        "motif.png",
        _asset_png(),
        target_layer_id=layer.layer_id,
    )
    session.move_object(source.object_id, x=100, y=80)
    session.copy_object()

    first = session.paste_object()
    second = session.paste_object()
    third = session.paste_object()

    assert (first.transform.x, first.transform.y) == (124, 104)
    assert (second.transform.x, second.transform.y) == (148, 128)
    assert (third.transform.x, third.transform.y) == (172, 152)


def test_clipboard_survives_switching_to_a_new_project() -> None:
    session = ProjectSession()
    session.new_project(title="Source", creator="Perajin")
    layer = session.create_object_layer("Source Layer")
    source = session.import_batik_asset(
        "motif.png",
        _asset_png(),
        target_layer_id=layer.layer_id,
    )
    session.copy_object(source.object_id)

    project = session.new_project(title="Destination", creator="Perajin")
    pasted = session.paste_object()

    assert len(project.layers) == 1
    assert project.layers[0].name == "Objek Tempel"
    assert project.layers[0].objects == (pasted,)
    assert pasted.asset_ref is not None
    assert pasted.asset_ref in session.assets


def test_copy_requires_an_active_object() -> None:
    session = ProjectSession()
    session.new_project(title="Empty", creator="Perajin")

    with pytest.raises(ProjectSessionError, match="Pilih satu objek"):
        session.copy_object()


def test_paste_requires_an_object_clipboard() -> None:
    session = ProjectSession()
    session.new_project(title="Empty", creator="Perajin")

    with pytest.raises(ProjectSessionError, match="Clipboard objek masih kosong"):
        session.paste_object()


def test_copy_paste_and_shifted_tool_shortcuts_are_conflict_free() -> None:
    assert OBJECT_COPY_SEQUENCE == "<Control-c>"
    assert OBJECT_PASTE_SEQUENCE == "<Control-v>"
    assert SELECT_TOOL_SEQUENCE == "<Shift-Key-V>"
    assert ISEN_TOOL_SEQUENCE == "<Shift-Key-C>"
