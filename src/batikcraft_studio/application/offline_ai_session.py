"""Application services for offline LoRA packs and rectangle-to-Batik selection."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageColor

from batikcraft_studio.ai import (
    BatikModelError,
    InstalledBatikModel,
    OfflineLoraBatificationProvider,
    OfflineModelLibrary,
    OfflineRuntimeConfig,
)
from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    Transform,
)
from batikcraft_studio.imaging.project_renderer import render_project_preview
from batikcraft_studio.imaging.structured_batification import (
    BatificationRequest,
    LocalStructuredBatificationProvider,
)

from .session import ProjectSessionError
from .structured_batification_session import (
    BatificationGeneration,
    StructuredBatificationProjectSession,
)


@dataclass(frozen=True, slots=True)
class OfflineRuntimeSelection:
    """Session-only selection of installed weights and local runtime folders."""

    model_id: str
    base_model_path: Path
    controlnet_path: Path | None
    device: str
    precision: str


class OfflineAIProjectSession(StructuredBatificationProjectSession):
    """Combine model-pack management, local inference, and canvas area selection."""

    def __init__(self, model_root: Path | str | None = None) -> None:
        super().__init__()
        self._model_library = OfflineModelLibrary(model_root)
        self._runtime_selection: OfflineRuntimeSelection | None = None

    @property
    def model_library(self) -> OfflineModelLibrary:
        return self._model_library

    @property
    def runtime_selection(self) -> OfflineRuntimeSelection | None:
        return self._runtime_selection

    @property
    def installed_models(self) -> tuple[InstalledBatikModel, ...]:
        return self._model_library.models

    def install_model_pack(
        self,
        path: Path | str,
        *,
        replace: bool = False,
    ) -> InstalledBatikModel:
        try:
            return self._model_library.install(path, replace=replace)
        except BatikModelError as exc:
            raise ProjectSessionError(str(exc)) from exc

    def uninstall_model_pack(self, model_id: str) -> None:
        if self._runtime_selection is not None and self._runtime_selection.model_id == model_id:
            self.use_foundation_renderer()
        try:
            self._model_library.uninstall(model_id)
        except BatikModelError as exc:
            raise ProjectSessionError(str(exc)) from exc

    def configure_offline_model(
        self,
        model_id: str,
        *,
        base_model_path: Path | str,
        controlnet_path: Path | str | None = None,
        device: str = "auto",
        precision: str = "auto",
        inference_steps: int = 28,
        guidance_scale: float = 7.0,
        controlnet_scale: float = 0.85,
        lora_scale: float | None = None,
        cpu_offload: bool = False,
    ) -> OfflineRuntimeSelection:
        """Activate an installed LoRA with local-only base and ControlNet weights."""

        try:
            model = self._model_library.get(model_id)
            config = OfflineRuntimeConfig(
                base_model_path=Path(base_model_path),
                controlnet_path=None if controlnet_path is None else Path(controlnet_path),
                device=device,
                precision=precision,
                inference_steps=inference_steps,
                guidance_scale=guidance_scale,
                controlnet_scale=controlnet_scale,
                lora_scale=lora_scale,
                cpu_offload=cpu_offload,
            )
            provider = OfflineLoraBatificationProvider(model, config)
        except (BatikModelError, RuntimeError) as exc:
            raise ProjectSessionError(str(exc)) from exc
        previous = self._batification_provider
        if isinstance(previous, OfflineLoraBatificationProvider):
            previous.unload()
        self.set_batification_provider(provider)
        selection = OfflineRuntimeSelection(
            model_id=model.model_id,
            base_model_path=config.base_model_path,
            controlnet_path=config.controlnet_path,
            device=config.device,
            precision=config.precision,
        )
        self._runtime_selection = selection
        return selection

    def use_foundation_renderer(self) -> None:
        previous = self._batification_provider
        if isinstance(previous, OfflineLoraBatificationProvider):
            previous.unload()
        self.set_batification_provider(LocalStructuredBatificationProvider())
        self._runtime_selection = None

    def batify_rectangle_selection(
        self,
        bounds: tuple[float, float, float, float],
        *,
        request: BatificationRequest,
        name: str = "Seleksi AI",
    ) -> BatificationGeneration:
        """Snapshot a canvas rectangle and Batify it as one Undo transaction."""

        project = self.require_project()
        left, top, right, bottom = _normalized_bounds(bounds)
        if right - left < 4 or bottom - top < 4:
            raise ProjectSessionError("Area seleksi AI terlalu kecil.")
        if left < 0 or top < 0 or right > project.canvas.width or bottom > project.canvas.height:
            raise ProjectSessionError("Area seleksi AI harus berada di dalam canvas.")
        content = _render_selection_png(self, (left, top, right, bottom))
        target, add_target = self._selection_target_layer()
        asset_ref = f"assets/{uuid4()}.png"
        with Image.open(BytesIO(content)) as image:
            pixel_width, pixel_height = image.size
        item = LayerObject(
            name=name[:120],
            kind=ObjectKind.RASTER,
            asset_ref=asset_ref,
            visible=True,
            locked=False,
            transform=Transform(
                x=(left + right) / 2,
                y=(top + bottom) / 2,
                scale_x=(right - left) / pixel_width,
                scale_y=(bottom - top) / pixel_height,
            ),
            bounds=ObjectBounds(pixel_width, pixel_height),
            properties={
                "source_format": "AI_SELECTION",
                "source_asset_ref": asset_ref,
                "asset_category": "ornamen",
                "ai_selection_source": True,
                "ai_selection_bounds": [left, top, right, bottom],
            },
        )
        before = self._capture_state()
        try:
            if add_target:
                project.add_layer(target, select=False)
            self._assets[asset_ref] = content
            project.add_object(target.layer_id, item, select=True)
            plan = self._plan_generation(item, request)
            self._commit_generation_plans((plan,))
        except Exception:
            self._restore_state(before)
            raise
        if self._undo_stack:
            self._undo_stack[-1] = before
        return plan.generation

    def _selection_target_layer(self) -> tuple[Layer, bool]:
        project = self.require_project()
        candidate_id = project.active_layer_id
        if candidate_id is not None:
            candidate = project.get_layer(candidate_id)
            if (
                candidate.node_kind is LayerNodeKind.LAYER
                and candidate.asset_ref is None
                and not project.is_layer_effectively_locked(candidate.layer_id)
            ):
                return candidate, False
        return (
            Layer(
                name="Seleksi AI",
                kind=LayerKind.BATIKIFIED_OBJECT,
                node_kind=LayerNodeKind.LAYER,
                properties={"object_container": True, "object_role": "ai-selection"},
            ),
            True,
        )


def _normalized_bounds(
    bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (float(value) for value in bounds)
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _render_selection_png(
    session: OfflineAIProjectSession,
    bounds: tuple[float, float, float, float],
) -> bytes:
    project = session.require_project()
    max_side = 2048
    rendered = render_project_preview(
        project,
        session.assets,
        max_width=min(project.canvas.width, max_side),
        max_height=min(project.canvas.height, max_side),
    )
    left, top, right, bottom = bounds
    scale = rendered.scale
    crop_box = (
        max(0, round(left * scale)),
        max(0, round(top * scale)),
        min(rendered.image.width, round(right * scale)),
        min(rendered.image.height, round(bottom * scale)),
    )
    crop = rendered.image.crop(crop_box).convert("RGBA")
    if crop.width < 1 or crop.height < 1:
        raise ProjectSessionError("Area seleksi AI tidak menghasilkan image.")
    canvas_rgb = ImageColor.getrgb(project.canvas.background_color)
    pixels = bytearray(crop.tobytes())
    for index in range(0, len(pixels), 4):
        distance = (
            abs(pixels[index] - canvas_rgb[0])
            + abs(pixels[index + 1] - canvas_rgb[1])
            + abs(pixels[index + 2] - canvas_rgb[2])
        )
        if distance <= 24:
            pixels[index + 3] = 0
    isolated = Image.frombytes("RGBA", crop.size, bytes(pixels))
    if isolated.getchannel("A").getbbox() is None:
        raise ProjectSessionError(
            "Area seleksi tidak memiliki garis atau objek yang berbeda dari warna canvas."
        )
    output = BytesIO()
    isolated.save(output, format="PNG", optimize=True)
    return output.getvalue()


__all__ = ["OfflineAIProjectSession", "OfflineRuntimeSelection"]
