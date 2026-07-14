"""Application services that coordinate domain, persistence, and UI workflows."""

from batikcraft_studio.application.asset_edit_session import EditableObjectProjectSession
from batikcraft_studio.application.batik_session import (
    BatikProjectSession,
    CapIsenError,
)
from batikcraft_studio.application.interactive_transform_session import (
    InteractiveTransformProjectSession,
)
from batikcraft_studio.application.motif_session import (
    MotifCapError,
    MotifProjectSession,
)
from batikcraft_studio.application.object_session import (
    ObjectLockedError,
    ObjectProjectSession,
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

# The public desktop session includes nested folders, multi-object layers, paint-stroke
# objects, editable Batik assets, humanize, shapes, isen, motif, and live WYSIWYG
# object transforms with one-step Undo/Redo.
ProjectSession = InteractiveTransformProjectSession

__all__ = [
    "BatikProjectSession",
    "CapIsenError",
    "EditableObjectProjectSession",
    "InteractiveTransformProjectSession",
    "LayerLockedError",
    "MotifCapError",
    "MotifProjectSession",
    "NoActiveProjectError",
    "ObjectLockedError",
    "ObjectProjectSession",
    "PaintLayerError",
    "PaintProjectSession",
    "ProjectPathRequiredError",
    "ProjectSession",
    "ProjectSessionError",
    "ProjectSessionSnapshot",
    "ShapeLayerError",
    "ShapeProjectSession",
]
