"""Application services that coordinate domain, persistence, and UI workflows."""

from batikcraft_studio.application.asset_edit_session import EditableObjectProjectSession
from batikcraft_studio.application.batik_session import (
    BatikProjectSession,
    CapIsenError,
)
from batikcraft_studio.application.clipboard_session import (
    ClipboardProjectSession,
    ObjectClipboardSnapshot,
)
from batikcraft_studio.application.interactive_transform_session import (
    InteractiveTransformProjectSession,
)
from batikcraft_studio.application.motif_session import (
    MotifCapError,
    MotifProjectSession,
)
from batikcraft_studio.application.multi_object_session import (
    GROUP_ID_KEY,
    GROUP_NAME_KEY,
    MultiObjectProjectSession,
    MultiObjectSelection,
)
from batikcraft_studio.application.object_session import (
    ObjectLockedError,
    ObjectProjectSession,
)
from batikcraft_studio.application.offline_ai_session import (
    OfflineAIProjectSession,
    OfflineRuntimeSelection,
)
from batikcraft_studio.application.paint_session import (
    PaintLayerError,
    PaintProjectSession,
)
from batikcraft_studio.application.process_session import (
    BATIK_PROCESS_EXTENSION,
    BatikProcessProjectSession,
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
from batikcraft_studio.application.structured_batification_session import (
    BatificationGeneration,
    StructuredBatificationProjectSession,
)

# The public desktop session now includes process documentation on top of offline AI and
# multi-object editing. Process data lives in a hidden non-rendering group node.
ProjectSession = BatikProcessProjectSession

__all__ = [
    "BATIK_PROCESS_EXTENSION",
    "GROUP_ID_KEY",
    "GROUP_NAME_KEY",
    "BatikProcessProjectSession",
    "BatikProjectSession",
    "BatificationGeneration",
    "CapIsenError",
    "ClipboardProjectSession",
    "EditableObjectProjectSession",
    "InteractiveTransformProjectSession",
    "LayerLockedError",
    "MotifCapError",
    "MotifProjectSession",
    "MultiObjectProjectSession",
    "MultiObjectSelection",
    "NoActiveProjectError",
    "ObjectClipboardSnapshot",
    "ObjectLockedError",
    "ObjectProjectSession",
    "OfflineAIProjectSession",
    "OfflineRuntimeSelection",
    "PaintLayerError",
    "PaintProjectSession",
    "ProjectPathRequiredError",
    "ProjectSession",
    "ProjectSessionError",
    "ProjectSessionSnapshot",
    "ShapeLayerError",
    "ShapeProjectSession",
    "StructuredBatificationProjectSession",
]
