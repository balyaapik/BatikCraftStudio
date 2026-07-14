"""Immutable production-plan values for written Batik workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from batikcraft_studio.domain.errors import ProjectValidationError

PROCESS_SCHEMA_VERSION = "1.0"
_HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class DyeSourceKind(StrEnum):
    NATURAL = "natural"
    SYNTHETIC = "synthetic"
    MIXED = "mixed"


class ProcessAction(StrEnum):
    SKETCH = "sketch"
    CANTING_OUTLINE = "canting_outline"
    CANTING_ISEN = "canting_isen"
    WAX_BLOCK = "wax_block"
    DYE_BATH = "dye_bath"
    DRY = "dry"
    WAX_REMOVAL = "wax_removal"
    FINISHING = "finishing"


def _text(value: object, label: str, maximum: int, *, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ProjectValidationError(f"{label} must be a string.")
    text = value.strip()
    if required and not text:
        raise ProjectValidationError(f"{label} must not be blank.")
    if len(text) > maximum:
        raise ProjectValidationError(f"{label} must contain at most {maximum} characters.")
    return text


def _uuid(value: object, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ProjectValidationError(f"{label} must be a valid UUID.") from exc


def _optional_uuid(value: object, label: str) -> str | None:
    if value is None or value == "":
        return None
    return _uuid(value, label)


@dataclass(frozen=True, slots=True)
class DyeSource:
    name: str
    kind: DyeSourceKind = DyeSourceKind.NATURAL
    material: str = ""
    plant_part: str = ""
    origin: str = ""
    notes: str = ""
    source_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _uuid(self.source_id, "source_id"))
        object.__setattr__(self, "name", _text(self.name, "source name", 120))
        try:
            kind = DyeSourceKind(self.kind)
        except (ValueError, TypeError) as exc:
            raise ProjectValidationError("Unsupported dye source kind.") from exc
        object.__setattr__(self, "kind", kind)
        for name, maximum in (
            ("material", 160),
            ("plant_part", 120),
            ("origin", 160),
            ("notes", 1_000),
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name, maximum, required=False))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.source_id,
            "name": self.name,
            "kind": self.kind.value,
            "material": self.material,
            "plant_part": self.plant_part,
            "origin": self.origin,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: object) -> DyeSource:
        if not isinstance(data, dict):
            raise ProjectValidationError("Dye source data must be an object.")
        return cls(
            source_id=data.get("id", str(uuid4())),
            name=data.get("name", ""),
            kind=data.get("kind", DyeSourceKind.NATURAL.value),
            material=data.get("material", ""),
            plant_part=data.get("plant_part", ""),
            origin=data.get("origin", ""),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True, slots=True)
class ColorRecipe:
    name: str
    hex_color: str
    source_ids: tuple[str, ...] = ()
    mordant: str = ""
    ratio: str = ""
    bath_temperature_celsius: float | None = None
    notes: str = ""
    recipe_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipe_id", _uuid(self.recipe_id, "recipe_id"))
        object.__setattr__(self, "name", _text(self.name, "recipe name", 120))
        color = _text(self.hex_color, "recipe color", 7).upper()
        if not _HEX_PATTERN.fullmatch(color):
            raise ProjectValidationError("Recipe color must use #RRGGBB.")
        object.__setattr__(self, "hex_color", color)
        source_ids = tuple(dict.fromkeys(_uuid(value, "source_id") for value in self.source_ids))
        object.__setattr__(self, "source_ids", source_ids)
        object.__setattr__(self, "mordant", _text(self.mordant, "mordant", 160, required=False))
        object.__setattr__(self, "ratio", _text(self.ratio, "ratio", 160, required=False))
        object.__setattr__(self, "notes", _text(self.notes, "notes", 1_000, required=False))
        if self.bath_temperature_celsius is not None:
            temperature = float(self.bath_temperature_celsius)
            if not -20 <= temperature <= 150:
                raise ProjectValidationError("Bath temperature is outside the supported range.")
            object.__setattr__(self, "bath_temperature_celsius", temperature)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.recipe_id,
            "name": self.name,
            "hex_color": self.hex_color,
            "source_ids": list(self.source_ids),
            "mordant": self.mordant,
            "ratio": self.ratio,
            "bath_temperature_celsius": self.bath_temperature_celsius,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: object) -> ColorRecipe:
        if not isinstance(data, dict):
            raise ProjectValidationError("Color recipe data must be an object.")
        return cls(
            recipe_id=data.get("id", str(uuid4())),
            name=data.get("name", ""),
            hex_color=data.get("hex_color", "#000000"),
            source_ids=tuple(data.get("source_ids", ())),
            mordant=data.get("mordant", ""),
            ratio=data.get("ratio", ""),
            bath_temperature_celsius=data.get("bath_temperature_celsius"),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True, slots=True)
class ProcessStep:
    name: str
    action: ProcessAction
    object_ids: tuple[str, ...] = ()
    group_ids: tuple[str, ...] = ()
    recipe_id: str | None = None
    duration_minutes: int | None = None
    notes: str = ""
    step_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", _uuid(self.step_id, "step_id"))
        object.__setattr__(self, "name", _text(self.name, "step name", 160))
        try:
            action = ProcessAction(self.action)
        except (ValueError, TypeError) as exc:
            raise ProjectValidationError("Unsupported process action.") from exc
        object.__setattr__(self, "action", action)
        object.__setattr__(
            self,
            "object_ids",
            tuple(dict.fromkeys(_uuid(value, "object_id") for value in self.object_ids)),
        )
        object.__setattr__(
            self,
            "group_ids",
            tuple(dict.fromkeys(_uuid(value, "group_id") for value in self.group_ids)),
        )
        object.__setattr__(self, "recipe_id", _optional_uuid(self.recipe_id, "recipe_id"))
        if self.duration_minutes is not None:
            if isinstance(self.duration_minutes, bool) or not isinstance(self.duration_minutes, int):
                raise ProjectValidationError("duration_minutes must be an integer.")
            if not 0 <= self.duration_minutes <= 100_000:
                raise ProjectValidationError("duration_minutes is outside the supported range.")
        object.__setattr__(self, "notes", _text(self.notes, "notes", 2_000, required=False))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.step_id,
            "name": self.name,
            "action": self.action.value,
            "object_ids": list(self.object_ids),
            "group_ids": list(self.group_ids),
            "recipe_id": self.recipe_id,
            "duration_minutes": self.duration_minutes,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: object) -> ProcessStep:
        if not isinstance(data, dict):
            raise ProjectValidationError("Process step data must be an object.")
        return cls(
            step_id=data.get("id", str(uuid4())),
            name=data.get("name", ""),
            action=data.get("action", ProcessAction.SKETCH.value),
            object_ids=tuple(data.get("object_ids", ())),
            group_ids=tuple(data.get("group_ids", ())),
            recipe_id=data.get("recipe_id"),
            duration_minutes=data.get("duration_minutes"),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True, slots=True)
class BatikProcessPlan:
    title: str = "Proses Pembuatan Batik"
    fabric: str = "Katun"
    technique: str = "Batik tulis"
    notes: str = ""
    dye_sources: tuple[DyeSource, ...] = ()
    color_recipes: tuple[ColorRecipe, ...] = ()
    steps: tuple[ProcessStep, ...] = ()
    plan_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _uuid(self.plan_id, "plan_id"))
        object.__setattr__(self, "title", _text(self.title, "plan title", 160))
        object.__setattr__(self, "fabric", _text(self.fabric, "fabric", 120))
        object.__setattr__(self, "technique", _text(self.technique, "technique", 120))
        object.__setattr__(self, "notes", _text(self.notes, "notes", 4_000, required=False))
        sources = tuple(self.dye_sources)
        recipes = tuple(self.color_recipes)
        steps = tuple(self.steps)
        if any(not isinstance(value, DyeSource) for value in sources):
            raise ProjectValidationError("dye_sources contains an invalid value.")
        if any(not isinstance(value, ColorRecipe) for value in recipes):
            raise ProjectValidationError("color_recipes contains an invalid value.")
        if any(not isinstance(value, ProcessStep) for value in steps):
            raise ProjectValidationError("steps contains an invalid value.")
        source_ids = {value.source_id for value in sources}
        recipe_ids = {value.recipe_id for value in recipes}
        if len(source_ids) != len(sources) or len(recipe_ids) != len(recipes):
            raise ProjectValidationError("Process IDs must be unique.")
        if any(source_id not in source_ids for recipe in recipes for source_id in recipe.source_ids):
            raise ProjectValidationError("A color recipe references a missing dye source.")
        if any(step.recipe_id not in recipe_ids for step in steps if step.recipe_id is not None):
            raise ProjectValidationError("A process step references a missing color recipe.")
        object.__setattr__(self, "dye_sources", sources)
        object.__setattr__(self, "color_recipes", recipes)
        object.__setattr__(self, "steps", steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROCESS_SCHEMA_VERSION,
            "id": self.plan_id,
            "title": self.title,
            "fabric": self.fabric,
            "technique": self.technique,
            "notes": self.notes,
            "dye_sources": [value.to_dict() for value in self.dye_sources],
            "color_recipes": [value.to_dict() for value in self.color_recipes],
            "steps": [value.to_dict() for value in self.steps],
        }

    @classmethod
    def from_dict(cls, data: object) -> BatikProcessPlan:
        if not isinstance(data, dict):
            raise ProjectValidationError("Batik process plan must be an object.")
        version = data.get("schema_version", PROCESS_SCHEMA_VERSION)
        if version != PROCESS_SCHEMA_VERSION:
            raise ProjectValidationError("Unsupported Batik process schema version.")
        return cls(
            plan_id=data.get("id", str(uuid4())),
            title=data.get("title", "Proses Pembuatan Batik"),
            fabric=data.get("fabric", "Katun"),
            technique=data.get("technique", "Batik tulis"),
            notes=data.get("notes", ""),
            dye_sources=tuple(DyeSource.from_dict(value) for value in data.get("dye_sources", ())),
            color_recipes=tuple(
                ColorRecipe.from_dict(value) for value in data.get("color_recipes", ())
            ),
            steps=tuple(ProcessStep.from_dict(value) for value in data.get("steps", ())),
        )


__all__ = [
    "PROCESS_SCHEMA_VERSION",
    "BatikProcessPlan",
    "ColorRecipe",
    "DyeSource",
    "DyeSourceKind",
    "ProcessAction",
    "ProcessStep",
]
