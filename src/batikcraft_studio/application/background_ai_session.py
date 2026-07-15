"""Preview-first Stable Diffusion Batik background workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from batikcraft_studio.ai.pretrained_background import (
    AIBatikBackgroundOptions,
    AIBatikBackgroundResult,
    PretrainedBatikBackgroundProvider,
)
from batikcraft_studio.domain import Layer, LayerKind, LayerObject, ObjectBounds, ObjectKind, Transform
from batikcraft_studio.imaging.structured_batification import BatificationError

from .outline_cleanup_session import OutlineCleanupProjectSession
from .session import ProjectSessionError

_BACKGROUND_LAYER_FLAG = "ai_batik_background_layer"
_BACKGROUND_OBJECT_FLAG = "ai_batik_background"


@dataclass(frozen=True, slots=True)
class AIBatikBackgroundContext:
    """Project snapshot captured before the generation dialog starts inference."""

    project_id: str
    project_revision: int
    canvas_width: int
    canvas_height: int


@dataclass(frozen=True, slots=True)
class AIBatikBackgroundPreview:
    """Generated candidate that has not changed the active project."""

    context: AIBatikBackgroundContext
    options: AIBatikBackgroundOptions
    reference_name: str | None
    result: AIBatikBackgroundResult


class AIBatikBackgroundProjectSession(OutlineCleanupProjectSession):
    """Generate and atomically apply one dedicated Batik background layer."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._background_ai_provider = PretrainedBatikBackgroundProvider()

    @property
    def background_ai_provider(self) -> PretrainedBatikBackgroundProvider:
        return self._background_ai_provider

    def set_background_ai_provider(self, provider: Any) -> None:
        if not callable(getattr(provider, "render", None)):
            raise ProjectSessionError("Provider background AI tidak valid.")
        previous = self._background_ai_provider
        if previous is not provider and callable(getattr(previous, "unload", None)):
            previous.unload()
        self._background_ai_provider = provider

    def prepare_background_ai_context(self) -> AIBatikBackgroundContext:
        project = self.require_project()
        return AIBatikBackgroundContext(
            project_id=project.project_id,
            project_revision=project.revision,
            canvas_width=project.canvas.width,
            canvas_height=project.canvas.height,
        )

    def render_background_ai_preview(
        self,
        context: AIBatikBackgroundContext,
        options: AIBatikBackgroundOptions | None = None,
        *,
        reference_content: bytes | None = None,
        reference_name: str | None = None,
    ) -> AIBatikBackgroundPreview:
        """Run Stable Diffusion; safe to call from a worker thread."""

        if not isinstance(context, AIBatikBackgroundContext):
            raise ProjectSessionError("Konteks background AI tidak valid.")
        settings = options or AIBatikBackgroundOptions()
        try:
            result = self._background_ai_provider.render(
                context.canvas_width,
                context.canvas_height,
                settings,
                reference_content=reference_content,
                reference_name=reference_name,
            )
        except BatificationError as exc:
            raise ProjectSessionError(str(exc)) from exc
        return AIBatikBackgroundPreview(
            context=context,
            options=settings,
            reference_name=reference_name,
            result=result,
        )

    def commit_background_ai_preview(
        self,
        preview: AIBatikBackgroundPreview,
    ) -> LayerObject:
        """Create or replace the bottom background object as one Undo transaction."""

        if not isinstance(preview, AIBatikBackgroundPreview):
            raise ProjectSessionError("Preview background AI tidak valid.")
        project = self.require_project()
        context = preview.context
        if project.project_id != context.project_id:
            raise ProjectSessionError(
                "Project berubah saat background AI dibuat. Generate ulang pada project aktif."
            )
        if project.revision != context.project_revision:
            raise ProjectSessionError(
                "Project diedit saat background AI berjalan. Generate ulang sebelum menerapkan."
            )
        result = preview.result
        if not result.content or result.width < 1 or result.height < 1:
            raise ProjectSessionError("Hasil background AI tidak valid.")

        existing_layer: Layer | None = None
        existing_object: LayerObject | None = None
        for layer in project.layers:
            if layer.properties.get(_BACKGROUND_LAYER_FLAG) is True:
                existing_layer = layer
            for item in layer.objects:
                if item.properties.get(_BACKGROUND_OBJECT_FLAG) is True:
                    existing_layer = layer
                    existing_object = item
                    break
            if existing_object is not None:
                break

        asset_ref = f"assets/{uuid4()}.png"
        transform = Transform(
            x=project.canvas.width / 2,
            y=project.canvas.height / 2,
            scale_x=project.canvas.width / result.width,
            scale_y=project.canvas.height / result.height,
        )
        properties = {
            _BACKGROUND_OBJECT_FLAG: True,
            "source_format": "PRETRAINED_AI_BATIK_BACKGROUND_V1",
            "background_provider": result.provider_id,
            "background_settings": preview.options.to_properties(),
            "background_metadata": dict(result.metadata),
            "background_reference_name": preview.reference_name,
            "background_pretrained": True,
            "background_custom_training_required": False,
            "background_seamless": preview.options.seamless,
            "transformable": True,
            "humanized": False,
        }
        updated: LayerObject | None = None
        previous_ref = existing_object.asset_ref if existing_object is not None else None

        def mutation() -> None:
            nonlocal updated
            self._assets[asset_ref] = result.content
            if existing_object is not None and existing_layer is not None:
                updated = project.update_object(
                    existing_object.object_id,
                    name="AI Batik Background",
                    kind=ObjectKind.RASTER,
                    asset_ref=asset_ref,
                    visible=True,
                    locked=True,
                    opacity=1.0,
                    transform=transform,
                    bounds=ObjectBounds(result.width, result.height),
                    properties=properties,
                )
                layer_index = project.layers.index(project.get_layer(existing_layer.layer_id))
                if layer_index != 0:
                    project.reorder_layer(existing_layer.layer_id, 0)
            else:
                item = LayerObject(
                    name="AI Batik Background",
                    kind=ObjectKind.RASTER,
                    asset_ref=asset_ref,
                    visible=True,
                    locked=True,
                    opacity=1.0,
                    transform=transform,
                    bounds=ObjectBounds(result.width, result.height),
                    properties=properties,
                )
                layer = Layer(
                    name="AI Batik Background",
                    kind=LayerKind.RASTER,
                    locked=False,
                    properties={_BACKGROUND_LAYER_FLAG: True},
                    objects=(item,),
                )
                project.add_layer(layer, index=0, select=False)
                updated = item
            self._remove_asset_if_unreferenced(previous_ref)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Background AI tidak dapat diterapkan.")
        self.clear_object_selection()
        return project.get_object(updated.object_id)

    def unload_background_ai(self) -> None:
        unload = getattr(self._background_ai_provider, "unload", None)
        if callable(unload):
            unload()


__all__ = [
    "AIBatikBackgroundContext",
    "AIBatikBackgroundPreview",
    "AIBatikBackgroundProjectSession",
]
