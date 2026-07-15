"""Application services that coordinate domain, persistence, and UI workflows."""

from batikcraft_studio.application.asset_edit_session import EditableObjectProjectSession
from batikcraft_studio.application.background_ai_session import (
    AIBatikBackgroundContext,
    AIBatikBackgroundPreview,
    AIBatikBackgroundProjectSession,
)
from batikcraft_studio.application.batik_session import (
    BatikProjectSession,
    CapIsenError,
)
from batikcraft_studio.application.canvas_structure_session import (
    CanvasStructureProjectSession,
)
from batikcraft_studio.application.clipboard_session import (
    ClipboardProjectSession,
    ObjectClipboardSnapshot,
)
from batikcraft_studio.application.destructive_eraser_session import (
    DestructiveEraserProjectSession,
)
from batikcraft_studio.application.direct_style_session import DirectStyleProjectSession
from batikcraft_studio.application.external_image_session import ExternalImageProjectSession
from batikcraft_studio.application.gradient_session import (
    FILL_MODE_KEY,
    GRADIENT_KEY,
    GradientProjectSession,
)
from batikcraft_studio.application.hotfix_session import HotfixProjectSession
from batikcraft_studio.application.hotfix_session_v2 import FinalHotfixProjectSession
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
from batikcraft_studio.application.non_ml_batification_session import (
    NonMLBatificationPlan,
    NonMLBatificationPreview,
    NonMLBatificationProjectSession,
)
from batikcraft_studio.application.object_session import (
    ObjectLockedError,
    ObjectProjectSession,
)
from batikcraft_studio.application.offline_ai_session import (
    OfflineAIProjectSession,
    OfflineRuntimeSelection,
)
from batikcraft_studio.application.outline_cleanup_session import (
    OutlineCleanupPlan,
    OutlineCleanupPreview,
    OutlineCleanupProjectSession,
)
from batikcraft_studio.application.paint_session import (
    PaintLayerError,
    PaintProjectSession,
)
from batikcraft_studio.application.position_lock_session import (
    POSITION_LOCK_KEY,
    PositionLockedError,
    PositionLockProjectSession,
)
from batikcraft_studio.application.pretrained_ai_batification_session import (
    PretrainedAIBatificationProjectSession,
    PretrainedAIPlan,
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
from batikcraft_studio.application.viewport_session import (
    MultiObjectClipboardSnapshot,
    ViewportProjectSession,
)

# The desktop session includes AI backgrounds, pretrained Batification, image import,
# outline cleanup, and the existing manual editing stack.
ProjectSession = AIBatikBackgroundProjectSession

__all__ = [
    "BATIK_PROCESS_EXTENSION",
    "FILL_MODE_KEY",
    "GRADIENT_KEY",
    "GROUP_ID_KEY",
    "GROUP_NAME_KEY",
    "POSITION_LOCK_KEY",
    "AIBatikBackgroundContext",
    "AIBatikBackgroundPreview",
    "AIBatikBackgroundProjectSession",
    "BatikProcessProjectSession",
    "BatikProjectSession",
    "BatificationGeneration",
    "CanvasStructureProjectSession",
    "CapIsenError",
    "ClipboardProjectSession",
    "DestructiveEraserProjectSession",
    "DirectStyleProjectSession",
    "EditableObjectProjectSession",
    "ExternalImageProjectSession",
    "FinalHotfixProjectSession",
    "GradientProjectSession",
    "HotfixProjectSession",
    "InteractiveTransformProjectSession",
    "LayerLockedError",
    "MotifCapError",
    "MotifProjectSession",
    "MultiObjectClipboardSnapshot",
    "MultiObjectProjectSession",
    "MultiObjectSelection",
    "NoActiveProjectError",
    "NonMLBatificationPlan",
    "NonMLBatificationPreview",
    "NonMLBatificationProjectSession",
    "ObjectClipboardSnapshot",
    "ObjectLockedError",
    "ObjectProjectSession",
    "OfflineAIProjectSession",
    "OfflineRuntimeSelection",
    "OutlineCleanupPlan",
    "OutlineCleanupPreview",
    "OutlineCleanupProjectSession",
    "PaintLayerError",
    "PaintProjectSession",
    "PositionLockedError",
    "PositionLockProjectSession",
    "PretrainedAIBatificationProjectSession",
    "PretrainedAIPlan",
    "ProjectPathRequiredError",
    "ProjectSession",
    "ProjectSessionError",
    "ProjectSessionSnapshot",
    "ShapeLayerError",
    "ShapeProjectSession",
    "StructuredBatificationProjectSession",
    "ViewportProjectSession",
]
