"""Non-destructive structured Batification sessions.

Each generation keeps the original source object, creates a separate render object, and
optionally creates a separately editable isen/filler object. The implementation is provider
agnostic so a future AI backend can replace the deterministic local foundation renderer.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from batikcraft_studio.domain import LayerNodeKind, LayerObject, ObjectBounds, ObjectKind
from batikcraft_studio.imaging.structured_batification import (
    BatificationError,
    BatificationRequest,
    BatificationStyle,
    LocalStructuredBatificationProvider,
    StructuredBatificationProvider,
    renderable_source_content,
)

from .clipboard_session import ClipboardProjectSession
from .session import ProjectSessionError

_ROLE_KEY = "batification_role"
_SOURCE_ROLE = "source"
_RENDER_ROLE = "render"
_SUGGESTION_ROLE = "suggestion"
_SOURCE_ID_KEY = "batification_source_object_id"
_SOURCE_IDS_KEY = "batification_source_object_ids"
_GENERATION_KEY = "batification_generation_id"
_VERSION_KEY = "batification_version"
_SETTINGS_KEY = "batification_settings"
_PROVIDER_KEY = "batification_provider"
_RENDER_IDS_KEY = "batification_render_ids"
_ACTIVE_RENDER_KEY = "batification_active_render_id"
_GENERATION_COUNT_KEY = "batification_generation_count"


@dataclass(frozen=True, slots=True)
class BatificationGeneration:
    """Identifiers for one source-preserving structured generation."""

    source_object_id: str
    render_object_id: str
    suggestion_object_ids: tuple[str, ...]
    generation_id: str
    version: int
    provider_id: str


@dataclass(frozen=True, slots=True)
class _GenerationPlan:
    source: LayerObject
    layer_id: str
    render: LayerObject
    suggestions: tuple[LayerObject, ...]
    render_content: bytes
    suggestion_contents: tuple[bytes, ...]
    generation: BatificationGeneration


class StructuredBatificationProjectSession(ClipboardProjectSession):
    """Add object-aware Batification generations to the desktop session."""

    def __init__(self) -> None:
        super().__init__()
        self._batification_provider: StructuredBatificationProvider = (
            LocalStructuredBatificationProvider()
        )

    @property
    def batification_provider_id(self) -> str:
        return self._batification_provider.provider_id

    def set_batification_provider(
        self,
        provider: StructuredBatificationProvider,
    ) -> None:
        if not getattr(provider, "provider_id", "") or not callable(
            getattr(provider, "render", None)
        ):
            raise ProjectSessionError("Provider Batification tidak valid.")
        self._batification_provider = provider

    def batify_object(
        self,
        object_id: str | None = None,
        *,
        request: BatificationRequest | None = None,
    ) -> BatificationGeneration:
        """Render one source object and preserve every component independently."""

        project = self.require_project()
        source = self._resolve_source_object(object_id)
        plan = self._plan_generation(source, request or BatificationRequest())
        self._commit_generation_plans((plan,))
        project.set_active_object(plan.render.object_id)
        return plan.generation

    def batify_active_group(
        self,
        layer_id: str | None = None,
        *,
        request: BatificationRequest | None = None,
    ) -> tuple[BatificationGeneration, ...]:
        """Render every source object in the selected layer/folder as one Undo step."""

        project = self.require_project()
        selected_layer_id = layer_id or project.active_layer_id
        if selected_layer_id is None:
            raise ProjectSessionError("Pilih lapis atau folder yang akan dibatifikasi.")
        layer = project.get_layer(selected_layer_id)
        target_layers = (
            (layer, *project.descendants_of(layer.layer_id))
            if layer.node_kind is LayerNodeKind.GROUP
            else (layer,)
        )
        sources = tuple(
            item
            for target in target_layers
            if target.node_kind is not LayerNodeKind.GROUP
            for item in target.objects
            if self._is_source_candidate(item)
        )
        if not sources:
            raise ProjectSessionError(
                "Lapis atau folder terpilih tidak memiliki komponen sumber yang dapat dirender."
            )
        active_request = request or BatificationRequest()
        plans = tuple(self._plan_generation(source, active_request) for source in sources)
        self._commit_generation_plans(plans)
        project.set_active_object(plans[-1].render.object_id)
        return tuple(plan.generation for plan in plans)

    def rerender_object(
        self,
        object_id: str | None = None,
        *,
        request: BatificationRequest | None = None,
    ) -> BatificationGeneration:
        """Create a new version while keeping old render components recoverable."""

        source = self._resolve_source_object(object_id)
        active_request = request or self._request_for_next_version(source.object_id)
        return self.batify_object(source.object_id, request=active_request)

    def show_batification_source(self, object_id: str | None = None) -> LayerObject:
        """Show the editable source and hide every generated component."""

        project = self.require_project()
        source = self._resolve_source_object(object_id)
        linked = self._linked_components(source.object_id)

        def mutation() -> None:
            project.update_object(source.object_id, visible=True)
            for item in linked:
                project.update_object(item.object_id, visible=False)
            project.set_active_object(source.object_id)

        self._commit_mutation(mutation)
        return project.get_object(source.object_id)

    def show_latest_batification(
        self,
        object_id: str | None = None,
    ) -> BatificationGeneration:
        """Show the newest render and its same-generation suggestions."""

        project = self.require_project()
        source = self._resolve_source_object(object_id)
        renders = self.generation_history(source.object_id)
        if not renders:
            raise ProjectSessionError("Objek belum memiliki hasil Batification.")
        latest = renders[-1]
        generation_id = str(latest.properties.get(_GENERATION_KEY, ""))
        linked = self._linked_components(source.object_id)

        def mutation() -> None:
            project.update_object(source.object_id, visible=False)
            for item in linked:
                visible = str(item.properties.get(_GENERATION_KEY, "")) == generation_id
                project.update_object(item.object_id, visible=visible)
            project.set_active_object(latest.object_id)

        self._commit_mutation(mutation)
        return self._generation_from_render(latest)

    def reset_batification(
        self,
        object_id: str | None = None,
        *,
        remove_generated: bool = True,
    ) -> LayerObject:
        """Restore the source, optionally removing all generated versions and assets."""

        project = self.require_project()
        source = self._resolve_source_object(object_id)
        self._require_unlocked_object(source.object_id)
        linked = self._linked_components(source.object_id)
        cleaned = {
            key: value
            for key, value in source.properties.items()
            if not key.startswith("batification_")
        }

        def mutation() -> None:
            if remove_generated:
                for item in linked:
                    project.remove_object(item.object_id)
            else:
                for item in linked:
                    project.update_object(item.object_id, visible=False)
            project.update_object(
                source.object_id,
                visible=True,
                properties=cleaned,
            )
            project.set_active_object(source.object_id)
            if remove_generated:
                self._remove_unreferenced_assets()

        self._commit_mutation(mutation)
        return project.get_object(source.object_id)

    def generation_history(self, object_id: str | None = None) -> tuple[LayerObject, ...]:
        """Return render objects for a source, sorted by generation version."""

        source = self._resolve_source_object(object_id)
        renders = [
            item
            for item in self._linked_components(source.object_id)
            if item.properties.get(_ROLE_KEY) == _RENDER_ROLE
        ]
        renders.sort(
            key=lambda item: (
                int(item.properties.get(_VERSION_KEY, 0)),
                item.object_id,
            )
        )
        return tuple(renders)

    def _plan_generation(
        self,
        source: LayerObject,
        request: BatificationRequest,
    ) -> _GenerationPlan:
        project = self.require_project()
        self._require_unlocked_object(source.object_id)
        try:
            source_content = renderable_source_content(source, self._assets)
            result = self._batification_provider.render(source_content, request)
        except BatificationError as exc:
            raise ProjectSessionError(str(exc)) from exc

        layer_id = project.object_layer_id(source.object_id)
        version = 1 + max(
            (
                int(item.properties.get(_VERSION_KEY, 0))
                for item in self._linked_components(source.object_id)
                if item.properties.get(_ROLE_KEY) == _RENDER_ROLE
            ),
            default=0,
        )
        generation_id = str(uuid4())
        render_ref = f"assets/{uuid4()}.png"
        render_properties = {
            key: value
            for key, value in source.properties.items()
            if key in {"geometry_shear_x", "geometry_shear_y"}
        }
        render_properties.update(
            {
                _ROLE_KEY: _RENDER_ROLE,
                _SOURCE_ID_KEY: source.object_id,
                _GENERATION_KEY: generation_id,
                _VERSION_KEY: version,
                _SETTINGS_KEY: request.to_properties(),
                _PROVIDER_KEY: result.provider_id,
                "batification_metadata": dict(result.metadata),
                "batification_editable_component": True,
                "batification_rerenderable": True,
            }
        )
        render = LayerObject(
            name=_versioned_name(source.name, "Batik", version),
            kind=ObjectKind.MOTIF if source.kind is ObjectKind.RASTER else source.kind,
            asset_ref=render_ref,
            visible=True,
            locked=False,
            opacity=source.opacity,
            transform=source.transform,
            bounds=ObjectBounds(result.width, result.height),
            properties=render_properties,
        )

        suggestions: list[LayerObject] = []
        suggestion_contents: list[bytes] = []
        if result.filler_content:
            suggestion_ref = f"assets/{uuid4()}.png"
            suggestion_properties = {
                key: value
                for key, value in source.properties.items()
                if key in {"geometry_shear_x", "geometry_shear_y"}
            }
            suggestion_properties.update(
                {
                    _ROLE_KEY: _SUGGESTION_ROLE,
                    _SOURCE_ID_KEY: source.object_id,
                    _SOURCE_IDS_KEY: [source.object_id],
                    _GENERATION_KEY: generation_id,
                    _VERSION_KEY: version,
                    _SETTINGS_KEY: request.to_properties(),
                    _PROVIDER_KEY: result.provider_id,
                    "batification_suggestion_type": "isen-filler",
                    "batification_editable_component": True,
                }
            )
            suggestions.append(
                LayerObject(
                    name=_versioned_name(source.name, "Isen AI", version),
                    kind=ObjectKind.ISEN,
                    asset_ref=suggestion_ref,
                    visible=True,
                    locked=False,
                    opacity=min(1.0, source.opacity * 0.9),
                    transform=source.transform,
                    bounds=ObjectBounds(result.width, result.height),
                    properties=suggestion_properties,
                )
            )
            suggestion_contents.append(result.filler_content)

        generation = BatificationGeneration(
            source_object_id=source.object_id,
            render_object_id=render.object_id,
            suggestion_object_ids=tuple(item.object_id for item in suggestions),
            generation_id=generation_id,
            version=version,
            provider_id=result.provider_id,
        )
        return _GenerationPlan(
            source=source,
            layer_id=layer_id,
            render=render,
            suggestions=tuple(suggestions),
            render_content=result.content,
            suggestion_contents=tuple(suggestion_contents),
            generation=generation,
        )

    def _commit_generation_plans(self, plans: tuple[_GenerationPlan, ...]) -> None:
        project = self.require_project()

        def mutation() -> None:
            for plan in plans:
                linked = self._linked_components(plan.source.object_id)
                for previous in linked:
                    if previous.visible:
                        project.update_object(previous.object_id, visible=False)
                existing_ids = [
                    str(value)
                    for value in plan.source.properties.get(_RENDER_IDS_KEY, [])
                    if isinstance(value, str)
                ]
                source_properties = dict(plan.source.properties)
                source_properties.update(
                    {
                        _ROLE_KEY: _SOURCE_ROLE,
                        _RENDER_IDS_KEY: [*existing_ids, plan.render.object_id],
                        _ACTIVE_RENDER_KEY: plan.render.object_id,
                        _GENERATION_COUNT_KEY: plan.generation.version,
                    }
                )
                project.update_object(
                    plan.source.object_id,
                    visible=False,
                    properties=source_properties,
                )
                if plan.render.asset_ref is None:
                    raise ProjectSessionError("Hasil Batification tidak memiliki asset.")
                self._assets[plan.render.asset_ref] = plan.render_content
                project.add_object(plan.layer_id, plan.render, select=True)
                for suggestion, content in zip(
                    plan.suggestions,
                    plan.suggestion_contents,
                    strict=True,
                ):
                    if suggestion.asset_ref is None:
                        raise ProjectSessionError("Saran Batification tidak memiliki asset.")
                    self._assets[suggestion.asset_ref] = content
                    project.add_object(plan.layer_id, suggestion, select=False)

        self._commit_mutation(mutation)

    def _resolve_source_object(self, object_id: str | None) -> LayerObject:
        project = self.require_project()
        selected_id = object_id or project.active_object_id
        if selected_id is None:
            raise ProjectSessionError("Pilih objek pada canvas terlebih dahulu.")
        item = project.get_object(selected_id)
        role = item.properties.get(_ROLE_KEY)
        if role in {_RENDER_ROLE, _SUGGESTION_ROLE}:
            source_id = item.properties.get(_SOURCE_ID_KEY)
            if not isinstance(source_id, str):
                source_ids = item.properties.get(_SOURCE_IDS_KEY, [])
                source_id = next(
                    (value for value in source_ids if isinstance(value, str)),
                    None,
                )
            if not isinstance(source_id, str):
                raise ProjectSessionError("Komponen hasil tidak memiliki sumber yang valid.")
            return project.get_object(source_id)
        return item

    def _linked_components(self, source_object_id: str) -> tuple[LayerObject, ...]:
        project = self.require_project()
        result: list[LayerObject] = []
        for layer in project.layers:
            for item in layer.objects:
                if item.object_id == source_object_id:
                    continue
                direct = item.properties.get(_SOURCE_ID_KEY) == source_object_id
                source_ids = item.properties.get(_SOURCE_IDS_KEY, [])
                grouped = isinstance(source_ids, list) and source_object_id in source_ids
                if direct or grouped:
                    result.append(item)
        return tuple(result)

    def _is_source_candidate(self, item: LayerObject) -> bool:
        role = item.properties.get(_ROLE_KEY)
        return role not in {_RENDER_ROLE, _SUGGESTION_ROLE} and (
            item.kind is not ObjectKind.ERASER_STROKE
        )

    def _request_for_next_version(self, source_object_id: str) -> BatificationRequest:
        history = self.generation_history(source_object_id)
        if not history:
            return BatificationRequest()
        settings = history[-1].properties.get(_SETTINGS_KEY)
        if not isinstance(settings, dict):
            return BatificationRequest()
        try:
            return BatificationRequest(
                style=BatificationStyle(settings.get("style", "classic")),
                strength=settings.get("strength", 0.72),
                isen_density=settings.get("isen_density", 0.48),
                preserve_palette=bool(settings.get("preserve_palette", False)),
                primary_color=str(settings.get("primary_color", "#4E2A1E")),
                secondary_color=str(settings.get("secondary_color", "#D9A566")),
                seed=int(settings.get("seed", 2026)) + 1,
                add_filler=bool(settings.get("add_filler", True)),
                prompt=str(settings.get("prompt", "")),
            )
        except (BatificationError, TypeError, ValueError):
            return BatificationRequest()

    def _generation_from_render(self, item: LayerObject) -> BatificationGeneration:
        source_id = str(item.properties.get(_SOURCE_ID_KEY, ""))
        generation_id = str(item.properties.get(_GENERATION_KEY, ""))
        suggestions = tuple(
            component.object_id
            for component in self._linked_components(source_id)
            if component.properties.get(_ROLE_KEY) == _SUGGESTION_ROLE
            and component.properties.get(_GENERATION_KEY) == generation_id
        )
        return BatificationGeneration(
            source_object_id=source_id,
            render_object_id=item.object_id,
            suggestion_object_ids=suggestions,
            generation_id=generation_id,
            version=int(item.properties.get(_VERSION_KEY, 0)),
            provider_id=str(item.properties.get(_PROVIDER_KEY, "")),
        )


def _versioned_name(source_name: str, label: str, version: int) -> str:
    suffix = f" — {label} v{version}"
    maximum = max(1, 120 - len(suffix))
    return f"{source_name[:maximum].rstrip()}{suffix}"


__all__ = [
    "BatificationGeneration",
    "StructuredBatificationProjectSession",
]
