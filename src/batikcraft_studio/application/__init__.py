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

# The public session used by the desktop application includes paint commands while
# preserving every ProjectSession API from Milestones 2C and 2D.
ProjectSession = PaintProjectSession

__all__ = [
    "LayerLockedError",
    "NoActiveProjectError",
    "PaintLayerError",
    "PaintProjectSession",
    "ProjectPathRequiredError",
    "ProjectSession",
    "ProjectSessionError",
    "ProjectSessionSnapshot",
]
