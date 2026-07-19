from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from PIL import Image, ImageDraw

from batikcraft_studio.ai.default_batik_reference import build_default_batik_reference
from batikcraft_studio.ai.pretrained_batification import PretrainedAIBatificationOptions
from batikcraft_studio.application.pretrained_ai_batification_session import (
    PretrainedAIBatificationProjectSession,
)
from batikcraft_studio.domain import Layer, LayerObject, ObjectBounds, ObjectKind
from batikcraft_studio.ui.context_tool_editor_hotfix_v11 import (
    _AI_CONTEXT_LABEL,
    _NON_AI_CONTEXT_LABEL,
    ContextToolEditorWorkspaceView,
)


def _png() -> bytes:
    image = Image.new("RGBA", (64, 48), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((5, 4, 58, 43), radius=9, fill=(156, 143, 122, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_default_batik_reference_is_valid_deterministic_png() -> None:
    first = build_default_batik_reference(_png())
    second = build_default_batik_reference(_png())

    assert first == second
    with Image.open(BytesIO(first)) as image:
        image.load()
        assert image.format == "PNG"
        assert image.size == (256, 256)
        assert len(image.convert("RGB").getcolors(maxcolors=1_000_000) or ()) > 4


def test_single_selected_object_builds_ai_plan_with_generated_reference() -> None:
    session = PretrainedAIBatificationProjectSession()
    project = session.new_project(title="AI Object", creator="Balya Rochmadi")
    layer = Layer(name="Objects")
    project.add_layer(layer)
    source_ref = "assets/source.png"
    source = LayerObject(
        name="Wayang",
        kind=ObjectKind.RASTER,
        asset_ref=source_ref,
        bounds=ObjectBounds(64, 48),
    )
    project.add_object(layer.layer_id, source)
    session.replace_assets({source_ref: _png()})
    session.set_selected_objects([source.object_id])

    plan = session.prepare_selected_pretrained_ai(
        PretrainedAIBatificationOptions(
            model_id_or_path="local-test-model",
            inference_steps=2,
            resolution=256,
        )
    )

    assert plan.source_object_id == source.object_id
    assert plan.motif_object_id is None
    assert plan.uses_selected_motif is False
    with Image.open(BytesIO(plan.motif_content)) as motif:
        motif.load()
        assert motif.size == (256, 256)


class _FakeMenu:
    def __init__(self, labels: list[str]) -> None:
        self.entries: list[dict[str, object]] = [
            {"type": "command", "label": label, "command": None} for label in labels
        ]

    def index(self, value: str) -> int | None:
        assert value == "end"
        return len(self.entries) - 1 if self.entries else None

    def entrycget(self, index: int, option: str) -> object:
        return self.entries[index][option]

    def entryconfigure(self, index: int, **changes: object) -> None:
        self.entries[index].update(changes)

    def delete(self, index: int) -> None:
        del self.entries[index]

    def add_separator(self) -> None:
        self.entries.append({"type": "separator", "label": "", "command": None})

    def add_command(self, **values: object) -> None:
        self.entries.append({"type": "command", **values})


def test_context_menu_exposes_only_model_based_batification() -> None:
    menu = _FakeMenu(["Batifikasi Non-AI…"])
    editor = SimpleNamespace(
        _selection_context_menu=menu,
        batify_selected_with_pretrained_ai=lambda: None,
    )

    ContextToolEditorWorkspaceView._configure_object_batification_context_actions(editor)

    labels = [str(entry["label"]) for entry in menu.entries]
    # Batifikasi tanpa model sudah dihapus: entri lama harus dibuang dan hanya
    # aksi berbasis model yang tersedia.
    assert _NON_AI_CONTEXT_LABEL not in labels
    assert "Batifikasi Non-AI…" not in labels
    assert _AI_CONTEXT_LABEL in labels
    ai_entry = next(entry for entry in menu.entries if entry["label"] == _AI_CONTEXT_LABEL)
    assert callable(ai_entry["command"])
