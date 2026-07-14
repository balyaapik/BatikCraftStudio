"""Public project-domain API for BatikCraft Studio."""

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
    "CanvasSpec",
    "DuplicateLayerError",
    "DuplicateObjectError",
    "Layer",
    "LayerKind",
    "LayerNodeKind",
    "LayerNotFoundError",
    "LayerObject",
    "ObjectBounds",
    "ObjectKind",
    "ObjectNotFoundError",
    "Project",
    "ProjectDomainError",
    "ProjectMetadata",
    "ProjectValidationError",
    "Transform",
]
