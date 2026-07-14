from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from batikcraft_studio.application import OfflineAIProjectSession
from batikcraft_studio.imaging.structured_batification import BatificationRequest


def _line_art() -> bytes:
    image = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.line((20, 20, 100, 100), fill=(55, 31, 22, 255), width=12)
    draw.line((100, 20, 20, 100), fill=(55, 31, 22, 255), width=12)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_rectangle_selection_creates_source_render_and_filler_as_one_undo(
    tmp_path: Path,
) -> None:
    session = OfflineAIProjectSession(tmp_path / "models")
    session.new_project(
        title="Selection",
        creator="Tester",
        width=256,
        height=256,
    )
    original = session.import_raster_object("lines.png", _line_art())
    before_count = session.require_project().object_count

    generation = session.batify_rectangle_selection(
        (40, 40, 216, 216),
        request=BatificationRequest(
            prompt="jadikan ornamen wayang",
            add_filler=True,
        ),
    )

    project = session.require_project()
    assert project.object_count == before_count + 3
    source = project.get_object(generation.source_object_id)
    render = project.get_object(generation.render_object_id)
    filler = project.get_object(generation.suggestion_object_ids[0])
    assert source.properties["ai_selection_source"] is True
    assert source.visible is False
    assert render.visible is True
    assert filler.visible is True
    assert render.object_id != filler.object_id
    assert original.object_id != source.object_id

    assert session.undo() is True
    restored = session.require_project()
    assert restored.object_count == before_count
    assert restored.get_object(original.object_id).visible is True

    assert session.redo() is True
    assert session.require_project().object_count == before_count + 3


def test_selection_result_can_be_saved_and_reopened(tmp_path: Path) -> None:
    session = OfflineAIProjectSession(tmp_path / "models")
    session.new_project(title="Persist", creator="Tester", width=256, height=256)
    session.import_raster_object("lines.png", _line_art())
    generation = session.batify_rectangle_selection(
        (40, 40, 216, 216),
        request=BatificationRequest(prompt="jadikan motif batik"),
    )
    path = tmp_path / "selection.batikcraft"
    session.save_as(path)

    reopened = OfflineAIProjectSession(tmp_path / "models-2")
    reopened.open_project(path)
    project = reopened.require_project()

    assert project.get_object(generation.render_object_id).properties[
        "batification_source_object_id"
    ] == generation.source_object_id
    assert project.get_object(generation.source_object_id).properties[
        "ai_selection_source"
    ] is True
