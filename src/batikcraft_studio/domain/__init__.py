"""Public project-domain API for BatikCraft Studio."""

from batikcraft_studio.domain.batik_process import (
    PROCESS_SCHEMA_VERSION,
    BatikProcessPlan,
    ColorRecipe,
    DyeSource,
    DyeSourceKind,
    ProcessAction,
    ProcessStep,
)
from batikcraft_studio.domain.errors import (
    DuplicateLayerError,
    DuplicateObjectError,
    LayerNotFoundError,
    ObjectNotFoundError,
    ProjectDomainError,
    ProjectValidationError,
)
from batikcraft_studio.domain.models import (
    CURRENT_SCHEMA_VERSION,
    LEGACY_SCHEMA_VERSIONS,
    MAX_CANVAS_DIMENSION,
    CanvasSpec,
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectBounds,
    ObjectKind,
    ProjectMetadata,
    Transform,
)
from batikcraft_studio.domain.project import Project

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "LEGACY_SCHEMA_VERSIONS",
    "MAX_CANVAS_DIMENSION",
    "PROCESS_SCHEMA_VERSION",
    "BatikProcessPlan",
    "CanvasSpec",
    "ColorRecipe",
    "DuplicateLayerError",
    "DuplicateObjectError",
    "DyeSource",
    "DyeSourceKind",
    "Layer",
    "LayerKind",
    "LayerNodeKind",
    "LayerNotFoundError",
    "LayerObject",
    "ObjectBounds",
    "ObjectKind",
    "ObjectNotFoundError",
    "ProcessAction",
    "ProcessStep",
    "Project",
    "ProjectDomainError",
    "ProjectMetadata",
    "ProjectValidationError",
    "Transform",
]
