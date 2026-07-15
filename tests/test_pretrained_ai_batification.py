"""Tests for pretrained img2img Batification without downloading real weights."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageOps

from batikcraft_studio.ai import (
    PretrainedAIBatificationOptions,
    PretrainedAIBatificationResult,
    PretrainedImg2ImgBatificationProvider,
)
from batikcraft_studio.application import (
    PretrainedAIBatificationProjectSession,
    ProjectSessionError,
)
from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    ObjectNotFoundError,
    Transform,
)


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _transparent_source() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 10, 55, 53), fill=(185, 185, 185, 255))
    draw.line((14, 34, 50, 34), fill=(40, 40, 40, 255), width=4)
    return image


def _motif() -> Image.Image:
    image = Image.new("RGBA", (20, 20), (235, 198, 105, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 9, 9), fill=(78, 42, 30, 255))
    draw.rectangle((10, 10, 19, 19), fill=(133, 36, 48, 255))
    draw.line((0, 19, 19, 0), fill=(36, 71, 94, 255), width=3)
    return image


class _FakeGenerator:
    def __init__(self, device: str) -> None:
        self.device = device
        self.seed = 0

    def manual_seed(self, seed: int) -> _FakeGenerator:
        self.seed = seed
        return self


class _FakeTorch:
    @staticmethod
    def Generator(device: str) -> _FakeGenerator:  # noqa: N802 - mimic torch API
        return _FakeGenerator(device)


class _FakePipeline:
    def __call__(self, **kwargs: object) -> SimpleNamespace:
        initial = kwargs["image"]
        assert isinstance(initial, Image.Image)
        gray = ImageOps.autocontrast(initial.convert("L"))
        generated = ImageOps.colorize(
            gray,
            black=(43, 25, 19),
            white=(218, 154, 72),
        ).convert("RGBA")
        return SimpleNamespace(
            images=[generated],
            nsfw_content_detected=[False],
        )


def _fake_factory(
    _options: PretrainedAIBatificationOptions,
) -> tuple[_FakePipeline, _FakeTorch, str]:
    return _FakePipeline(), _FakeTorch(), "cpu"


def test_pretrained_provider_preserves_source_alpha_and_uses_no_custom_training() -> None:
    provider = PretrainedImg2ImgBatificationProvider(_fake_factory)
    result = provider.render(
        _png(_transparent_source()),
        _png(_motif()),
        PretrainedAIBatificationOptions(
            model_id_or_path="fake/model",
            inference_steps=3,
            resolution=256,
            cpu_offload=False,
        ),
    )

    rendered = Image.open(BytesIO(result.content)).convert("RGBA")
    assert rendered.size == (64, 64)
    assert rendered.getpixel((0, 0))[3] == 0
    assert rendered.getpixel((32, 32))[3] > 0
    assert result.provider_id == "pretrained-img2img:fake/model"
    assert result.metadata["pretrained"] is True
    assert result.metadata["custom_training_required"] is False
    assert result.metadata["motif_palette"]


def test_pretrained_options_reject_invalid_values() -> None:
    with pytest.raises(Exception, match="strength"):
        PretrainedAIBatificationOptions(strength=1.5)
    with pytest.raises(Exception, match="resolution"):
        PretrainedAIBatificationOptions(resolution=128)


class _SessionFakeProvider:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.unloaded = False

    def render(
        self,
        _source: bytes,
        _motif_content: bytes,
        options: PretrainedAIBatificationOptions,
    ) -> PretrainedAIBatificationResult:
        return PretrainedAIBatificationResult(
            content=self.content,
            width=64,
            height=64,
            provider_id="pretrained-img2img:test",
            metadata={
                "pretrained": True,
                "custom_training_required": False,
                "model_id_or_path": options.model_id_or_path,
            },
        )

    def unload(self) -> None:
        self.unloaded = True


def test_session_commits_ai_result_in_source_layer_as_one_undo_step() -> None:
    session = PretrainedAIBatificationProjectSession()
    project = session.new_project(title="AI Batification", creator="Test", width=160, height=120)
    layer = Layer(
        name="Objects",
        kind=LayerKind.BATIKIFIED_OBJECT,
        node_kind=LayerNodeKind.LAYER,
        properties={"object_container": True},
    )
    project.add_layer(layer)

    source_ref = "assets/source.png"
    motif_ref = "assets/motif.png"
    session._assets[source_ref] = _png(_transparent_source())
    session._assets[motif_ref] = _png(_motif())
    source = LayerObject(
        name="Random object",
        kind=ObjectKind.RASTER,
        asset_ref=source_ref,
        transform=Transform(x=60, y=60),
        bounds=ObjectBounds(64, 64),
    )
    motif = LayerObject(
        name="Batik motif",
        kind=ObjectKind.MOTIF,
        asset_ref=motif_ref,
        transform=Transform(x=120, y=60),
        bounds=ObjectBounds(20, 20),
    )
    project.add_object(layer.layer_id, source, select=False)
    project.add_object(layer.layer_id, motif, select=False)
    session.set_selected_objects([source.object_id, motif.object_id])
    session.set_pretrained_ai_provider(_SessionFakeProvider(_png(_transparent_source())))

    plan = session.prepare_selected_pretrained_ai(
        PretrainedAIBatificationOptions(model_id_or_path="fake/model")
    )
    rendered = session.render_pretrained_ai_plan(plan)
    output = session.commit_pretrained_ai_result(plan, rendered)

    objects = project.get_layer(layer.layer_id).objects
    assert project.object_layer_id(output.object_id) == layer.layer_id
    assert project.get_object(source.object_id).visible is False
    assert project.get_object(motif.object_id).visible is True
    assert output.properties["batification_pretrained"] is True
    assert len(objects) == 3

    assert session.undo() is True
    assert project.get_object(source.object_id).visible is True
    with pytest.raises(ObjectNotFoundError):
        project.get_object(output.object_id)

    assert session.redo() is True
    assert project.get_object(source.object_id).visible is False
    assert project.get_object(output.object_id).visible is True


def test_stale_ai_result_is_rejected_after_project_edit() -> None:
    session = PretrainedAIBatificationProjectSession()
    project = session.new_project(title="Stale", creator="Test", width=100, height=100)
    layer = Layer(
        name="Objects",
        kind=LayerKind.BATIKIFIED_OBJECT,
        node_kind=LayerNodeKind.LAYER,
        properties={"object_container": True},
    )
    project.add_layer(layer)
    source_ref = "assets/source.png"
    motif_ref = "assets/motif.png"
    session._assets[source_ref] = _png(_transparent_source())
    session._assets[motif_ref] = _png(_motif())
    source = LayerObject(
        name="Source",
        kind=ObjectKind.RASTER,
        asset_ref=source_ref,
        bounds=ObjectBounds(64, 64),
    )
    motif = LayerObject(
        name="Motif",
        kind=ObjectKind.MOTIF,
        asset_ref=motif_ref,
        bounds=ObjectBounds(20, 20),
    )
    project.add_object(layer.layer_id, source, select=False)
    project.add_object(layer.layer_id, motif, select=False)
    session.set_selected_objects([source.object_id, motif.object_id])
    provider = _SessionFakeProvider(_png(_transparent_source()))
    session.set_pretrained_ai_provider(provider)
    plan = session.prepare_selected_pretrained_ai(
        PretrainedAIBatificationOptions(model_id_or_path="fake/model")
    )
    result = session.render_pretrained_ai_plan(plan)

    project.update_object(source.object_id, opacity=0.8)
    with pytest.raises(ProjectSessionError, match="diedit saat AI berjalan"):
        session.commit_pretrained_ai_result(plan, result)
