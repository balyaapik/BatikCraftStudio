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

# The public desktop session includes model packs, rectangle selection, and local-only LoRA
# inference in addition to the source-preserving Milestone 4A workflow.
ProjectSession = OfflineAIProjectSession

__all__ = [
    "BatikProjectSession",
    "BatificationGeneration",
    "CapIsenError",
    "ClipboardProjectSession",
    "EditableObjectProjectSession",
    "InteractiveTransformProjectSession",
    "LayerLockedError",
    "MotifCapError",
    "MotifProjectSession",
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
