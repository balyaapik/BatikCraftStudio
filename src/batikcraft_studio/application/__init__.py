"""Application services that coordinate domain, persistence, and UI workflows."""

from batikcraft_studio.application.batik_session import (
    BatikProjectSession,
    CapIsenError,
)
from batikcraft_studio.application.motif_session import (
    MotifCapError,
    MotifProjectSession,
)
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

# The public desktop session includes raster, paint, shape, isen, and motif-pokok
# commands while preserving every ProjectSession API from the earlier milestones.
ProjectSession = MotifProjectSession

__all__ = [
    "BatikProjectSession",
    "CapIsenError",
    "LayerLockedError",
    "MotifCapError",
    "MotifProjectSession",
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
