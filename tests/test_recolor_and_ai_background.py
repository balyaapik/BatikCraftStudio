from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from batikcraft_studio.ai import (
    AIBatikBackgroundOptions,
    AIBatikBackgroundResult,
)
from batikcraft_studio.application import AIBatikBackgroundProjectSession
from batikcraft_studio.ui.context_tool_editor_hotfix_v9 import (
    apply_palette_color_to_current_selection,
)


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _outline_png() -> bytes:
    image = Image.new("RGBA", (40, 32), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((5, 5, 34, 26), outline=(0, 0, 0, 255), width=4)
    return _png(image)


class _FakeBackgroundProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, str | None]] = []
        self.color = (80, 120, 160, 255)

    def render(
        self,
        canvas_width: int,
        canvas_height: int,
        options: AIBatikBackgroundOptions,
        *,
        reference_content: bytes | None = None,
        reference_name: str | None = None,
    ) -> AIBatikBackgroundResult:
        self.calls.append((canvas_width, canvas_height, reference_name))
        image = Image.new("RGBA", (64, 48), self.color)
        return AIBatikBackgroundResult(
            content=_png(image),
            width=64,
            height=48,
            provider_id="fake-background",
            metadata={"mode": "img2img" if reference_content else "text2img"},
        )

    def unload(self) -> None:
        return None


def test_clicked_palette_color_recolors_selected_raster_and_preserves_alpha() -> None:
    session = AIBatikBackgroundProjectSession()
    session.new_project(title="Recolor", creator="Test", width=300, height=200)
    item = session.import_external_image("outline.png", _outline_png())
    original_content = session._assets[item.asset_ref]  # noqa: SLF001 - verify stored pixels

    updated = apply_palette_color_to_current_selection(session, "#D2665A")

    assert len(updated) == 1
    result = updated[0]
    assert result.object_id == item.object_id
    assert result.asset_ref != item.asset_ref
    with Image.open(BytesIO(original_content)) as before, Image.open(
        BytesIO(session._assets[result.asset_ref])  # noqa: SLF001 - verify stored pixels
    ) as after:
        before_rgba = before.convert("RGBA")
        after_rgba = after.convert("RGBA")
        assert before_rgba.getchannel("A").tobytes() == after_rgba.getchannel("A").tobytes()
        assert after_rgba.getpixel((5, 5))[:3] == (210, 102, 90)
        assert after_rgba.getpixel((0, 0))[3] == 0


def test_ai_background_preview_is_pure_and_commit_creates_bottom_locked_layer() -> None:
    session = AIBatikBackgroundProjectSession()
    session.new_project(title="Background", creator="Test", width=400, height=300)
    session.import_external_image("foreground.png", _outline_png())
    provider = _FakeBackgroundProvider()
    session.set_background_ai_provider(provider)
    project = session.require_project()
    original_revision = project.revision
    context = session.prepare_background_ai_context()

    preview = session.render_background_ai_preview(
        context,
        AIBatikBackgroundOptions(seed=77, resolution=512),
        reference_content=_outline_png(),
        reference_name="Kawung",
    )

    assert project.revision == original_revision
    assert provider.calls == [(400, 300, "Kawung")]

    applied = session.commit_background_ai_preview(preview)

    assert project.layers[0].name == "AI Batik Background"
    assert project.layers[0].objects == (applied,)
    assert applied.locked is True
    assert applied.properties["ai_batik_background"] is True
    assert applied.transform.x == 200
    assert applied.transform.y == 150
    assert applied.transform.scale_x == 400 / 64
    assert applied.transform.scale_y == 300 / 48


def test_regenerating_background_replaces_same_object_and_is_undoable() -> None:
    session = AIBatikBackgroundProjectSession()
    session.new_project(title="Background", creator="Test", width=320, height=240)
    provider = _FakeBackgroundProvider()
    session.set_background_ai_provider(provider)

    first_context = session.prepare_background_ai_context()
    first_preview = session.render_background_ai_preview(first_context)
    first = session.commit_background_ai_preview(first_preview)
    first_ref = first.asset_ref

    provider.color = (180, 90, 60, 255)
    second_context = session.prepare_background_ai_context()
    second_preview = session.render_background_ai_preview(
        second_context,
        AIBatikBackgroundOptions(seed=88, resolution=512),
    )
    second = session.commit_background_ai_preview(second_preview)

    backgrounds = [
        item
        for layer in session.require_project().layers
        for item in layer.objects
        if item.properties.get("ai_batik_background") is True
    ]
    assert len(backgrounds) == 1
    assert second.object_id == first.object_id
    assert second.asset_ref != first_ref

    session.undo()
    restored = session.require_project().get_object(first.object_id)
    assert restored.asset_ref == first_ref

    session.redo()
    redone = session.require_project().get_object(first.object_id)
    assert redone.asset_ref == second.asset_ref
