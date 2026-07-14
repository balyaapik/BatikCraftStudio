from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from batikcraft_studio.application import StructuredBatificationProjectSession
from batikcraft_studio.imaging.structured_batification import (
    BatificationRequest,
    BatificationStyle,
    LocalStructuredBatificationProvider,
)


def _source_png(color: tuple[int, int, int, int] = (126, 70, 36, 255)) -> bytes:
    image = Image.new("RGBA", (96, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 88, 72), fill=color, outline=(54, 29, 18, 255), width=5)
    draw.line((20, 40, 76, 40), fill=(242, 210, 153, 255), width=5)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _session() -> StructuredBatificationProjectSession:
    session = StructuredBatificationProjectSession()
    session.new_project(title="Structured", creator="Balya Rochmadi", width=512, height=512)
    return session


def test_local_provider_returns_separate_deterministic_components() -> None:
    provider = LocalStructuredBatificationProvider()
    request = BatificationRequest(
        style=BatificationStyle.CLASSIC,
        seed=77,
        add_filler=True,
    )

    first = provider.render(_source_png(), request)
    second = provider.render(_source_png(), request)

    assert first.content == second.content
    assert first.filler_content == second.filler_content
    assert first.filler_content is not None
    assert first.provider_id == "local-structured-foundation-v1"
    assert first.metadata["foundation_renderer"] is True


def test_object_batification_keeps_source_render_and_filler_separate() -> None:
    session = _session()
    layer = session.create_object_layer("Komposisi")
    source = session.import_raster_object(
        "bunga.png",
        _source_png(),
        target_layer_id=layer.layer_id,
    )

    generation = session.batify_object(
        source.object_id,
        request=BatificationRequest(seed=11, add_filler=True),
    )
    project = session.require_project()
    source_after = project.get_object(source.object_id)
    render = project.get_object(generation.render_object_id)
    filler = project.get_object(generation.suggestion_object_ids[0])

    assert project.object_count == 3
    assert source_after.visible is False
    assert source_after.properties["batification_role"] == "source"
    assert render.visible is True
    assert render.object_id != source.object_id
    assert render.properties["batification_role"] == "render"
    assert render.properties["batification_source_object_id"] == source.object_id
    assert render.properties["batification_version"] == 1
    assert filler.visible is True
    assert filler.properties["batification_role"] == "suggestion"
    assert filler.kind.value == "isen"
    assert source.asset_ref in session.assets
    assert render.asset_ref in session.assets
    assert filler.asset_ref in session.assets


def test_rerender_versions_can_toggle_back_to_source_and_latest() -> None:
    session = _session()
    source = session.import_raster_object("daun.png", _source_png())
    first = session.batify_object(source.object_id)
    second = session.rerender_object(first.render_object_id)

    project = session.require_project()
    first_render = project.get_object(first.render_object_id)
    second_render = project.get_object(second.render_object_id)
    assert first.version == 1
    assert second.version == 2
    assert first_render.visible is False
    assert second_render.visible is True
    assert len(session.generation_history(source.object_id)) == 2

    shown_source = session.show_batification_source(second_render.object_id)
    assert shown_source.object_id == source.object_id
    assert shown_source.visible is True
    assert all(not item.visible for item in session.generation_history(source.object_id))

    latest = session.show_latest_batification(source.object_id)
    assert latest.version == 2
    assert project.get_object(source.object_id).visible is False
    assert project.get_object(second.render_object_id).visible is True


def test_group_batification_is_one_undo_step() -> None:
    session = _session()
    folder = session.create_folder("Tema Flora")
    layer = session.create_object_layer("Bunga dan Daun", parent_id=folder.layer_id)
    session.import_raster_object(
        "bunga.png",
        _source_png(),
        target_layer_id=layer.layer_id,
    )
    session.import_raster_object(
        "daun.png",
        _source_png((61, 112, 70, 255)),
        target_layer_id=layer.layer_id,
    )
    before = session.require_project().object_count
    session.select_layer(folder.layer_id)

    generations = session.batify_active_group(request=BatificationRequest(seed=99))

    assert len(generations) == 2
    assert session.require_project().object_count == before + 4
    session.undo()
    assert session.require_project().object_count == before


def test_reset_removes_generated_components_and_assets() -> None:
    session = _session()
    source = session.import_raster_object("kawung.png", _source_png())
    generation = session.batify_object(source.object_id)
    generated_refs = {
        session.require_project().get_object(generation.render_object_id).asset_ref,
        *(
            session.require_project().get_object(item_id).asset_ref
            for item_id in generation.suggestion_object_ids
        ),
    }

    restored = session.reset_batification(
        generation.render_object_id,
        remove_generated=True,
    )

    assert restored.object_id == source.object_id
    assert restored.visible is True
    assert session.require_project().object_count == 1
    assert not any(key.startswith("batification_") for key in restored.properties)
    assert all(asset_ref not in session.assets for asset_ref in generated_refs)


def test_structured_generations_survive_project_save_and_reopen(tmp_path: Path) -> None:
    session = _session()
    source = session.import_raster_object("truntum.png", _source_png())
    generation = session.batify_object(
        source.object_id,
        request=BatificationRequest(
            style=BatificationStyle.INDIGO,
            primary_color="#102A43",
            secondary_color="#D9EAF7",
            seed=123,
        ),
    )
    destination = tmp_path / "structured.batikcraft"
    session.save_as(destination)

    reopened = StructuredBatificationProjectSession()
    project = reopened.open_project(destination)
    render = project.get_object(generation.render_object_id)

    assert render.properties["batification_role"] == "render"
    assert render.properties["batification_settings"]["style"] == "indigo"
    assert render.asset_ref in reopened.assets
    assert len(reopened.generation_history(source.object_id)) == 1
