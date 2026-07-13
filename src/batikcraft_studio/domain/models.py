"""Immutable value objects used by the BatikCraft project aggregate."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID, uuid4

from batikcraft_studio.domain.errors import ProjectValidationError

CURRENT_SCHEMA_VERSION = "1.0"
MAX_CANVAS_DIMENSION = 16_384
_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _validate_non_blank(value: str, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ProjectValidationError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ProjectValidationError(f"{field_name} must not be blank.")
    if len(normalized) > maximum:
        raise ProjectValidationError(
            f"{field_name} must contain at most {maximum} characters."
        )
    return normalized


def _validate_finite(value: float, field_name: str) -> float:
    if isinstance(value, bool):
        raise ProjectValidationError(f"{field_name} must be numeric.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ProjectValidationError(f"{field_name} must be numeric.") from exc
    if not math.isfinite(numeric):
        raise ProjectValidationError(f"{field_name} must be finite.")
    return numeric


def _validate_uuid(value: str, field_name: str) -> str:
    try:
        normalized = str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ProjectValidationError(f"{field_name} must be a valid UUID.") from exc
    return normalized


class LayerKind(StrEnum):
    """Supported layer categories at the project-domain boundary."""

    RASTER = "raster"
    PAINT = "paint"
    SHAPE = "shape"
    BATIKIFIED_OBJECT = "batikified_object"


@dataclass(frozen=True, slots=True)
class ProjectMetadata:
    """Human-readable project information."""

    title: str
    creator: str
    description: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        title = _validate_non_blank(self.title, "title", 120)
        creator = _validate_non_blank(self.creator, "creator", 120)
        if not isinstance(self.description, str):
            raise ProjectValidationError("description must be a string.")
        description = self.description.strip()
        if len(description) > 2_000:
            raise ProjectValidationError(
                "description must contain at most 2000 characters."
            )
        if isinstance(self.tags, str):
            raise ProjectValidationError("tags must be a sequence of strings.")

        normalized_tags: list[str] = []
        seen: set[str] = set()
        for raw_tag in self.tags:
            tag = _validate_non_blank(raw_tag, "tag", 40)
            lookup_key = tag.casefold()
            if lookup_key not in seen:
                normalized_tags.append(tag)
                seen.add(lookup_key)
        if len(normalized_tags) > 20:
            raise ProjectValidationError("A project may contain at most 20 tags.")

        object.__setattr__(self, "title", title)
        object.__setattr__(self, "creator", creator)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "tags", tuple(normalized_tags))


@dataclass(frozen=True, slots=True)
class CanvasSpec:
    """Logical dimensions and background of the motif workspace."""

    width: int = 2048
    height: int = 2048
    background_color: str = "#F4E9D8"

    def __post_init__(self) -> None:
        if isinstance(self.width, bool) or not isinstance(self.width, int):
            raise ProjectValidationError("canvas width must be an integer.")
        if isinstance(self.height, bool) or not isinstance(self.height, int):
            raise ProjectValidationError("canvas height must be an integer.")
        if not 1 <= self.width <= MAX_CANVAS_DIMENSION:
            raise ProjectValidationError(
                f"canvas width must be between 1 and {MAX_CANVAS_DIMENSION}."
            )
        if not 1 <= self.height <= MAX_CANVAS_DIMENSION:
            raise ProjectValidationError(
                f"canvas height must be between 1 and {MAX_CANVAS_DIMENSION}."
            )
        if not isinstance(self.background_color, str) or not _HEX_COLOR_PATTERN.fullmatch(
            self.background_color
        ):
            raise ProjectValidationError(
                "background_color must use the #RRGGBB hexadecimal format."
            )
        object.__setattr__(self, "background_color", self.background_color.upper())


@dataclass(frozen=True, slots=True)
class Transform:
    """Non-destructive placement information for a workspace layer."""

    x: float = 0.0
    y: float = 0.0
    rotation_degrees: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0

    def __post_init__(self) -> None:
        values = {
            "x": _validate_finite(self.x, "transform x"),
            "y": _validate_finite(self.y, "transform y"),
            "rotation_degrees": _validate_finite(
                self.rotation_degrees, "rotation_degrees"
            ),
            "scale_x": _validate_finite(self.scale_x, "scale_x"),
            "scale_y": _validate_finite(self.scale_y, "scale_y"),
        }
        if values["scale_x"] == 0 or values["scale_y"] == 0:
            raise ProjectValidationError("Layer scales must not be zero.")
        for name, value in values.items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class Layer:
    """Immutable workspace layer descriptor.

    Binary image content is intentionally represented by ``asset_ref``. Actual file
    persistence belongs to Milestone 2B.
    """

    name: str
    kind: LayerKind = LayerKind.RASTER
    layer_id: str = field(default_factory=lambda: str(uuid4()))
    asset_ref: str | None = None
    visible: bool = True
    locked: bool = False
    opacity: float = 1.0
    transform: Transform = field(default_factory=Transform)
    properties: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        name = _validate_non_blank(self.name, "layer name", 120)
        layer_id = _validate_uuid(self.layer_id, "layer_id")
        try:
            kind = LayerKind(self.kind)
        except (TypeError, ValueError) as exc:
            raise ProjectValidationError(f"Unsupported layer kind: {self.kind!r}.") from exc
        if not isinstance(self.visible, bool):
            raise ProjectValidationError("visible must be a boolean.")
        if not isinstance(self.locked, bool):
            raise ProjectValidationError("locked must be a boolean.")
        if not isinstance(self.transform, Transform):
            raise ProjectValidationError("transform must be a Transform value object.")
        if not isinstance(self.properties, Mapping):
            raise ProjectValidationError("properties must be a mapping.")
        for key in self.properties:
            _validate_non_blank(key, "property key", 120)

        opacity = _validate_finite(self.opacity, "opacity")
        if not 0.0 <= opacity <= 1.0:
            raise ProjectValidationError("opacity must be between 0.0 and 1.0.")
        if self.asset_ref is not None:
            asset_ref = _validate_non_blank(self.asset_ref, "asset_ref", 500)
            object.__setattr__(self, "asset_ref", asset_ref)

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "layer_id", layer_id)
        object.__setattr__(self, "opacity", opacity)
        object.__setattr__(self, "properties", MappingProxyType(dict(self.properties)))

    def with_updates(self, **changes: Any) -> Layer:
        """Return a validated copy with selected fields replaced."""

        forbidden = {"layer_id"}.intersection(changes)
        if forbidden:
            raise ProjectValidationError("layer_id cannot be changed after creation.")
        allowed = {
            "name",
            "kind",
            "asset_ref",
            "visible",
            "locked",
            "opacity",
            "transform",
            "properties",
        }
        unknown = set(changes).difference(allowed)
        if unknown:
            joined = ", ".join(sorted(unknown))
            raise ProjectValidationError(f"Unknown layer update fields: {joined}.")
        return replace(self, **changes)
