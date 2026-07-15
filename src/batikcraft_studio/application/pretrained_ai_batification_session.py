"""Application workflow for pretrained AI Batification without custom training."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from batikcraft_studio.ai.pretrained_batification import (
    PretrainedAIBatificationOptions,
    PretrainedAIBatificationResult,
    PretrainedImg2ImgBatificationProvider,
)
from batikcraft_studio.domain import LayerObject, ObjectBounds, ObjectKind, Transform
from batikcraft_studio.imaging.structured_batification import (
    BatificationError,
    renderable_source_content,
)

from .non_ml_batification_session import NonMLBatificationProjectSession
from .session import ProjectSessionError


@dataclass(frozen=True, slots=True)
class PretrainedAIPlan:
    """Immutable inputs captured before model inference starts."""

    project_id: str
    project_revision: int
    source_object_id: str
    motif_object_id: str
    source_name: str
    source_layer_id: str
    source_index: int
    source_opacity: float
    source_transform: Transform
    source_content: bytes
    motif_content: bytes
    options: PretrainedAIBatificationOptions


class PretrainedAIBatificationProjectSession(NonMLBatificationProjectSession):
    """Add two-object Stable Diffusion img2img Batification to the desktop session."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._pretrained_ai_provider = PretrainedImg2ImgBatificationProvider()

    @property
    def pretrained_ai_provider(self) -> PretrainedImg2ImgBatificationProvider:
        return self._pretrained_ai_provider

    def set_pretrained_ai_provider(self, provider: Any) -> None:
        if not callable(getattr(provider, "render", None)):
            raise ProjectSessionError("Provider AI pretrained tidak valid.")
        previous = self._pretrained_ai_provider
        if previous is not provider and callable(getattr(previous, "unload", None)):
            previous.unload()
        self._pretrained_ai_provider = provider

    def prepare_selected_pretrained_ai(
        self,
        options: PretrainedAIBatificationOptions | None = None,
    ) -> PretrainedAIPlan:
        """Capture source first and motif second without running model inference."""

        selected = self.selected_object_ids
        if len(selected) != 2:
            raise ProjectSessionError(
                "Pilih tepat dua objek: objek sumber terlebih dahulu, lalu Shift-pilih motif batik."
            )
        return self.prepare_pretrained_ai(
            selected[0],
            selected[1],
            options=options,
        )

    def prepare_pretrained_ai(
        self,
        source_object_id: str,
        motif_object_id: str,
        *,
        options: PretrainedAIBatificationOptions | None = None,
    ) -> PretrainedAIPlan:
        if source_object_id == motif_object_id:
            raise ProjectSessionError("Objek sumber dan motif batik harus berbeda.")
        project = self.require_project()
        source = self._require_unlocked_object(source_object_id)
        motif = project.get_object(motif_object_id)
        if motif.kind is ObjectKind.ERASER_STROKE:
            raise ProjectSessionError("Goresan penghapus tidak dapat menjadi referensi motif AI.")
        try:
            source_content = renderable_source_content(source, self._assets)
            motif_content = renderable_source_content(motif, self._assets)
            settings = options or PretrainedAIBatificationOptions()
        except BatificationError as exc:
            raise ProjectSessionError(str(exc)) from exc

        layer_id = project.object_layer_id(source.object_id)
        layer = project.get_layer(layer_id)
        source_index = next(
            index
            for index, candidate in enumerate(layer.objects)
            if candidate.object_id == source.object_id
        )
        return PretrainedAIPlan(
            project_id=project.project_id,
            project_revision=project.revision,
            source_object_id=source.object_id,
            motif_object_id=motif.object_id,
            source_name=source.name,
            source_layer_id=layer_id,
            source_index=source_index,
            source_opacity=source.opacity,
            source_transform=source.transform,
            source_content=bytes(source_content),
            motif_content=bytes(motif_content),
            options=settings,
        )

    def render_pretrained_ai_plan(
        self,
        plan: PretrainedAIPlan,
    ) -> PretrainedAIBatificationResult:
        """Run model inference; safe to call from a worker thread."""

        try:
            return self._pretrained_ai_provider.render(
                plan.source_content,
                plan.motif_content,
                plan.options,
            )
        except BatificationError as exc:
            raise ProjectSessionError(str(exc)) from exc

    def commit_pretrained_ai_result(
        self,
        plan: PretrainedAIPlan,
        result: PretrainedAIBatificationResult,
    ) -> LayerObject:
        """Commit a completed worker result as one main-thread Undo transaction."""

        project = self.require_project()
        if project.project_id != plan.project_id:
            raise ProjectSessionError("Project berubah saat AI berjalan. Jalankan Batifikasi AI kembali.")
        if project.revision != plan.project_revision:
            raise ProjectSessionError(
                "Project diedit saat AI berjalan sehingga hasil lama tidak diterapkan. Jalankan kembali."
            )
        source = self._require_unlocked_object(plan.source_object_id)
        motif = project.get_object(plan.motif_object_id)
        if project.object_layer_id(source.object_id) != plan.source_layer_id:
            raise ProjectSessionError("Objek sumber berpindah layer saat AI berjalan. Jalankan kembali.")
        if not result.content or result.width < 1 or result.height < 1:
            raise ProjectSessionError("Hasil AI tidak valid.")

        asset_ref = f"assets/{uuid4()}.png"
        properties = {
            "source_format": "PRETRAINED_AI_BATIFICATION_V1",
            "batification_provider": result.provider_id,
            "batification_source_object_id": source.object_id,
            "batification_motif_object_id": motif.object_id,
            "batification_settings": plan.options.to_properties(),
            "batification_metadata": dict(result.metadata),
            "batification_pretrained": True,
            "batification_custom_training_required": False,
            "batification_non_destructive": True,
            "batification_editable_component": True,
        }
        output = LayerObject(
            name=f"Batifikasi AI {plan.source_name}"[:120],
            kind=ObjectKind.MOTIF,
            asset_ref=asset_ref,
            visible=True,
            locked=False,
            opacity=plan.source_opacity,
            transform=plan.source_transform,
            bounds=ObjectBounds(result.width, result.height),
            properties=properties,
        )

        def mutation() -> None:
            self._assets[asset_ref] = result.content
            project.update_object(source.object_id, visible=False)
            project.add_object(
                plan.source_layer_id,
                output,
                index=plan.source_index + 1,
                select=True,
            )

        self._commit_mutation(mutation)
        self.set_selected_objects([output.object_id])
        return project.get_object(output.object_id)

    def batify_selected_with_pretrained_ai(
        self,
        options: PretrainedAIBatificationOptions | None = None,
    ) -> LayerObject:
        """Synchronous convenience method for scripts and tests."""

        plan = self.prepare_selected_pretrained_ai(options)
        result = self.render_pretrained_ai_plan(plan)
        return self.commit_pretrained_ai_result(plan, result)

    def unload_pretrained_ai(self) -> None:
        unload = getattr(self._pretrained_ai_provider, "unload", None)
        if callable(unload):
            unload()


__all__ = [
    "PretrainedAIBatificationProjectSession",
    "PretrainedAIPlan",
]
