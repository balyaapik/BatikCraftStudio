"""Application services that coordinate domain, persistence, and UI workflows."""

from batikcraft_studio.application.paint_session import (
    PaintLayerError,
    PaintProjectSession,
)
from batikcraft_studio.application.session import (
    LayerLockedError,
    NoActiveProjectError,
    ProjectPathRequiredError,
    ProjectSessionError,
    ProjectSessionSnapshot,
)
from batikcraft_studio.application.shape_session import (
    ShapeLayerError,
    ShapeProjectSession,
)

# The public desktop session includes raster, paint, and non-destructive shape commands
# while preserving every ProjectSession API from the earlier milestones.
ProjectSession = ShapeProjectSession

__all__ = [
    "LayerLockedError",
    "NoActiveProjectError",
    "PaintLayerError",
    "PaintProjectSession",
    "ProjectPathRequiredError",
    "ProjectSession",
    "ProjectSessionError",
    "ProjectSessionSnapshot",
    "ShapeLayerError",
    "ShapeProjectSession",
]
