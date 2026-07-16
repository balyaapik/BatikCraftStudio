"""Application workflow for pretrained and BatikBrew AI generation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

from batikcraft_studio.ai.batikbrew_generation import (
    BatikBrewGenerationOptions,
    with_plan_context,
)
from batikcraft_studio.ai.default_batik_reference import build_default_batik_reference
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
    motif_object_id: str | None
    source_name: str
    source_layer_id: str
    source_index: int
    source_opacity: float
    source_transform: Transform
    source_content: bytes
    motif_content: bytes
    options: PretrainedAIBatificationOptions

    @property
    def uses_selected_motif(self) -> bool:
        return self.motif_object_id is not None


class PretrainedAIBatificationProjectSession(NonMLBatificationProjectSession):
    """Add object AI and notebook-compatible BatikBrew SDXL generation."""

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
        """Capture one source object and an optional second inspiration reference."""

        selected = self.selected_object_ids
        if len(selected) not in {1, 2}:
            raise ProjectSessionError(
                "Pilih satu objek sumber. Shift-pilih objek kedua bila ingin menggabungkan "
                "dua sumber inspirasi."
            )
        motif_object_id = selected[1] if len(selected) == 2 else None
        return self.prepare_pretrained_ai(
            selected[0],
            motif_object_id,
            options=options,
        )

    def prepare_pretrained_ai(
        self,
        source_object_id: str,
        motif_object_id: str | None = None,
        *,
        options: PretrainedAIBatificationOptions | None = None,
    ) -> PretrainedAIPlan:
        if motif_object_id is not None and source_object_id == motif_object_id:
            raise ProjectSessionError("Objek sumber dan referensi inspirasi harus berbeda.")
        project = self.require_project()
        source = self._require_unlocked_object(source_object_id)
        motif = None if motif_object_id is None else project.get_object(motif_object_id)
        if motif is not None and motif.kind is ObjectKind.ERASER_STROKE:
            raise ProjectSessionError("Goresan penghapus tidak dapat menjadi referensi AI.")
        try:
            source_content = renderable_source_content(source, self._assets)
            motif_content = (
                build_default_batik_reference(source_content)
                if motif is None
                else renderable_source_content(motif, self._assets)
            )
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
            motif_object_id=None if motif is None else motif.object_id,
            source_name=source.name,
            source_layer_id=layer_id,
            source_index=source_index,
            source_opacity=source.opacity,
            source_transform=source.transform,
            source_content=bytes(source_content),
            motif_content=bytes(motif_content),
            options=settings,
        )

    def render_pretrained_ai_variations(
        self,
        plan: PretrainedAIPlan,
    ) -> tuple[PretrainedAIBatificationResult, ...]:
        """Run one or more generations; safe to call from a worker thread."""

        options = plan.options
        if isinstance(options, BatikBrewGenerationOptions):
            options = with_plan_context(
                options,
                source_name=plan.source_name,
                use_secondary_reference=plan.uses_selected_motif,
            )
        try:
            render_many = getattr(self._pretrained_ai_provider, "render_variations", None)
            if callable(render_many):
                results = tuple(
                    render_many(
                        plan.source_content,
                        plan.motif_content,
                        options,
                    )
                )
            else:
                results = (
                    self._pretrained_ai_provider.render(
                        plan.source_content,
                        plan.motif_content,
                        options,
                    ),
                )
        except BatificationError as exc:
            raise ProjectSessionError(str(exc)) from exc
        if not results:
            raise ProjectSessionError("Provider AI tidak menghasilkan variasi gambar.")
        if any(not result.content or result.width < 1 or result.height < 1 for result in results):
            raise ProjectSessionError("Salah satu hasil AI tidak valid.")
        return results

    def render_pretrained_ai_plan(
        self,
        plan: PretrainedAIPlan,
    ) -> PretrainedAIBatificationResult:
        """Compatibility method returning the first generated variation."""

        return self.render_pretrained_ai_variations(plan)[0]

    def commit_pretrained_ai_result(
        self,
        plan: PretrainedAIPlan,
        result: PretrainedAIBatificationResult,
    ) -> LayerObject:
        """Commit a completed worker result as one main-thread Undo transaction."""

        project = self.require_project()
        if project.project_id != plan.project_id:
            raise ProjectSessionError(
                "Project berubah saat AI berjalan. Jalankan generasi AI kembali."
            )
        if project.revision != plan.project_revision:
            raise ProjectSessionError(
                "Project diedit saat AI berjalan sehingga hasil lama tidak diterapkan. "
                "Jalankan kembali."
            )
        source = self._require_unlocked_object(plan.source_object_id)
        motif = (
            None
            if plan.motif_object_id is None
            else project.get_object(plan.motif_object_id)
        )
        if project.object_layer_id(source.object_id) != plan.source_layer_id:
            raise ProjectSessionError(
                "Objek sumber berpindah layer saat AI berjalan. Jalankan kembali."
            )
        if not result.content or result.width < 1 or result.height < 1:
            raise ProjectSessionError("Hasil AI tidak valid.")

        metadata = dict(result.metadata)
        is_batikbrew = metadata.get("generation_mode") == "batikbrew_sdxl_text_to_image"
        asset_ref = f"assets/{uuid4()}.png"
        if is_batikbrew:
            motif_source = (
                "two_selected_inspirations" if motif is not None else "selected_inspiration"
            )
            source_format = "BATIKBREW_SDXL_GENERATION_V1"
            name = f"Motif BatikBrew dari {plan.source_name}"[:120]
            output_transform = _batikbrew_output_transform(source, result)
        else:
            motif_source = "selected_object" if motif is not None else "generated_batik_reference"
            source_format = "PRETRAINED_AI_BATIFICATION_V1"
            name = f"Batifikasi AI {plan.source_name}"[:120]
            output_transform = plan.source_transform

        properties = {
            "source_format": source_format,
            "batification_provider": result.provider_id,
            "batification_source_object_id": source.object_id,
            "batification_motif_object_id": None if motif is None else motif.object_id,
            "batification_motif_source": motif_source,
            "batification_settings": plan.options.to_properties(),
            "batification_metadata": metadata,
            "batification_pretrained": True,
            "batification_custom_training_required": False,
            "batification_non_destructive": True,
            "batification_editable_component": True,
            "batikbrew_generation": is_batikbrew,
        }
        output = LayerObject(
            name=name,
            kind=ObjectKind.MOTIF,
            asset_ref=asset_ref,
            visible=True,
            locked=False,
            opacity=plan.source_opacity,
            transform=output_transform,
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


def _batikbrew_output_transform(
    source: LayerObject,
    result: PretrainedAIBatificationResult,
) -> Transform:
    """Place a generated square near the visual footprint of its inspiration object."""

    displayed_width = source.bounds.width * abs(source.transform.scale_x)
    displayed_height = source.bounds.height * abs(source.transform.scale_y)
    target_side = max(64.0, displayed_width, displayed_height)
    scale = target_side / max(result.width, result.height)
    sign_x = -1.0 if source.transform.scale_x < 0 else 1.0
    sign_y = -1.0 if source.transform.scale_y < 0 else 1.0
    return replace(
        source.transform,
        scale_x=scale * sign_x,
        scale_y=scale * sign_y,
    )


__all__ = [
    "PretrainedAIBatificationProjectSession",
    "PretrainedAIPlan",
]
