"""Hasil AI harus dapat disalin-tempel seperti gambar canvas biasa."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from batikcraft_studio.application import PretrainedAIBatificationProjectSession
from batikcraft_studio.domain import (
    Layer,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Transform,
)


def _session_with_ai_result():
    session = PretrainedAIBatificationProjectSession()
    project = session.new_project(title="t", creator="t", width=800, height=600)
    buffer = BytesIO()
    Image.new("RGBA", (128, 128), (120, 70, 40, 255)).save(buffer, format="PNG")
    session._assets["assets/hasil.png"] = buffer.getvalue()

    result = LayerObject(
        name="Motif BatikBrew dari Botol",
        kind=ObjectKind.RASTER,
        asset_ref="assets/hasil.png",
        transform=Transform(x=400, y=300),
        bounds=ObjectBounds(128, 128),
        # Properti bernilai dict/list inilah yang dulu memecahkan paste.
        properties={
            "source_format": "BATIKBREW_SDXL_GENERATION_V1",
            "standalone_image": True,
            "batification_settings": {"lora_path": "/x/y.safetensors"},
            "batification_metadata": {"seed": 1, "steps": [1, 2, 3]},
        },
    )
    project.add_layer(Layer(name="L", objects=(result,)))
    project.set_active_object(result.object_id)
    return session, project, result


def test_ai_result_can_be_copied_and_pasted() -> None:
    """Regresi: paste gagal dengan 'unhashable type: dict' sehingga hasil AI
    hanya bisa digandakan lewat panel layer."""

    session, project, result = _session_with_ai_result()

    copied = session.copy_object()
    assert copied.object_id == result.object_id

    pasted = session.paste_object()
    assert pasted.object_id != result.object_id
    assert pasted.kind is ObjectKind.RASTER
    assert project.object_count == 2
    # Metadata bersarang tetap utuh setelah disalin.
    assert pasted.properties["batification_settings"]["lora_path"] == "/x/y.safetensors"
    assert pasted.properties["batification_metadata"]["steps"] == [1, 2, 3]


def test_pasting_twice_offsets_each_copy() -> None:
    session, project, result = _session_with_ai_result()
    session.copy_object()

    first = session.paste_object()
    second = session.paste_object()

    assert project.object_count == 3
    assert first.transform.x != second.transform.x
    # Setiap salinan memakai aset sendiri.
    assert first.asset_ref != result.asset_ref
    assert second.asset_ref not in (result.asset_ref, first.asset_ref)


def test_nested_asset_references_are_remapped() -> None:
    session, project, result = _session_with_ai_result()
    project.update_object(
        result.object_id,
        properties={
            **result.properties,
            "batification_settings": {"preview": "assets/hasil.png"},
        },
    )
    project.set_active_object(result.object_id)

    session.copy_object()
    pasted = session.paste_object()

    nested = pasted.properties["batification_settings"]["preview"]
    assert nested.startswith("assets/")
    assert nested != "assets/hasil.png"
    assert nested in session.assets


def test_copy_requires_a_selected_object() -> None:
    from batikcraft_studio.application.session import ProjectSessionError

    session = PretrainedAIBatificationProjectSession()
    session.new_project(title="t", creator="t", width=100, height=100)
    with pytest.raises(ProjectSessionError):
        session.copy_object()
