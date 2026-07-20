"""Application-wide configuration values.

Keep this module free from Tkinter imports so it can be reused by tests,
CLI utilities, project serializers, and future website integration code.
"""

from __future__ import annotations

from dataclasses import dataclass

APP_NAME = "BatikCraft Studio"
# Keep aligned with pyproject.toml and public installer filenames.
APP_VERSION = "0.3.9"
DEFAULT_WINDOW_SIZE = "1280x800"
MINIMUM_WINDOW_SIZE = (1024, 680)


@dataclass(frozen=True, slots=True)
class WorkspaceDefinition:
    """Metadata used to build navigation without coupling it to view classes."""

    key: str
    label: str
    eyebrow: str
    title: str
    description: str


WORKSPACES: tuple[WorkspaceDefinition, ...] = (
    WorkspaceDefinition(
        key="dashboard",
        label="Dashboard",
        eyebrow="PROJECT HOME",
        title="Create a motif with purpose",
        description=(
            "Start a new batik project, continue recent work, or review the next "
            "development milestones."
        ),
    ),
    WorkspaceDefinition(
        key="editor",
        label="Motif Editor",
        eyebrow="MANUAL WORKSPACE",
        title="Build the motif layer by layer",
        description=(
            "The editable canvas, layer manager, transform tools, and manual drawing "
            "tools will live in this workspace."
        ),
    ),
    WorkspaceDefinition(
        key="batikification",
        label="Object Batikfication",
        eyebrow="OBJECT TO MOTIF",
        title="Turn everyday objects into batik elements",
        description=(
            "Import an object, preserve its visual identity, apply a selected batik "
            "language, and send the result back to the main workspace."
        ),
    ),
    WorkspaceDefinition(
        key="preview",
        label="Pattern Preview",
        eyebrow="SEAMLESS PATTERN",
        title="Inspect how the tile repeats",
        description=(
            "Straight, mirror, half-drop, half-brick, and rotational repeat modes will "
            "be previewed here without changing the source motif."
        ),
    ),
    WorkspaceDefinition(
        key="publish",
        label="Publish",
        eyebrow="LICENSING BRIDGE",
        title="Prepare a licensable design version",
        description=(
            "Validate the project, render watermarked previews, configure licensing, "
            "and publish the motif to the BatikCraft website."
        ),
    ),
)


def get_workspace(key: str) -> WorkspaceDefinition:
    """Return a workspace definition or raise a clear error for invalid routes."""

    for workspace in WORKSPACES:
        if workspace.key == key:
            return workspace
    raise KeyError(f"Unknown workspace: {key}")
