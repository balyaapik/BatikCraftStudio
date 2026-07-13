"""Public project-domain API for BatikCraft Studio."""

from batikcraft_studio.domain.errors import (
    DuplicateLayerError,
    LayerNotFoundError,
    ProjectDomainError,
    ProjectValidationError,
)
from batikcraft_studio.domain.models import (
    CURRENT_SCHEMA_VERSION,
    MAX_CANVAS_DIMENSION,
    CanvasSpec,
    Layer,
    LayerKind,
    ProjectMetadata,
    Transform,
)
from batikcraft_studio.domain.project import Project

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "MAX_CANVAS_DIMENSION",
    "CanvasSpec",
    "DuplicateLayerError",
    "Layer",
    "LayerKind",
    "LayerNotFoundError",
    "Project",
    "ProjectDomainError",
    "ProjectMetadata",
    "ProjectValidationError",
    "Transform",
]
