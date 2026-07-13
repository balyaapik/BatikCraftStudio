"""Project-session service used by the Tkinter shell."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from batikcraft_studio.domain import CanvasSpec, Project
from batikcraft_studio.persistence import ProjectArchive


class ProjectSessionError(RuntimeError):
    """Base class for project-session failures."""


class NoActiveProjectError(ProjectSessionError):
    """Raised when an operation requires an active project."""


class ProjectPathRequiredError(ProjectSessionError):
    """Raised when Save is requested before a project has a file path."""


@dataclass(frozen=True, slots=True)
class ProjectSessionSnapshot:
    """Read-only project context suitable for presentation in the UI."""

    has_project: bool
    project_id: str | None = None
    title: str | None = None
    creator: str | None = None
    width: int | None = None
    height: int | None = None
    background_color: str | None = None
    path: Path | None = None
    dirty: bool = False
    layer_count: int = 0

    @property
    def display_path(self) -> str:
        return str(self.path) if self.path is not None else "Not saved yet"


class ProjectSession:
    """Coordinate the active project, its archive path, and embedded assets.

    The service deliberately contains no Tkinter imports. File dialogs and user
    confirmation remain UI responsibilities, while save/open rules stay testable.
    """

    def __init__(self) -> None:
        self._project: Project | None = None
        self._path: Path | None = None
        self._assets: dict[str, bytes] = {}

    @property
    def project(self) -> Project | None:
        return self._project

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def assets(self) -> Mapping[str, bytes]:
        return MappingProxyType(dict(self._assets))

    @property
    def has_project(self) -> bool:
        return self._project is not None

    @property
    def is_dirty(self) -> bool:
        return self._project.is_dirty if self._project is not None else False

    def snapshot(self) -> ProjectSessionSnapshot:
        project = self._project
        if project is None:
            return ProjectSessionSnapshot(has_project=False)
        return ProjectSessionSnapshot(
            has_project=True,
            project_id=project.project_id,
            title=project.metadata.title,
            creator=project.metadata.creator,
            width=project.canvas.width,
            height=project.canvas.height,
            background_color=project.canvas.background_color,
            path=self._path,
            dirty=project.is_dirty,
            layer_count=len(project.layers),
        )

    def new_project(
        self,
        *,
        title: str,
        creator: str,
        width: int = 2048,
        height: int = 2048,
        background_color: str = "#F4E9D8",
    ) -> Project:
        project = Project.create(
            title=title,
            creator=creator,
            canvas=CanvasSpec(
                width=width,
                height=height,
                background_color=background_color,
            ),
        )
        self._project = project
        self._path = None
        self._assets = {}
        return project

    def open_project(self, path: str | Path) -> Project:
        archive_path = Path(path)
        bundle = ProjectArchive.load(archive_path)
        self._project = bundle.project
        self._path = archive_path
        self._assets = dict(bundle.assets)
        return bundle.project

    def save(self) -> Path:
        project = self.require_project()
        if self._path is None:
            raise ProjectPathRequiredError("Use Save As before saving this project.")
        ProjectArchive.save(self._path, project, self._assets)
        return self._path

    def save_as(self, path: str | Path) -> Path:
        project = self.require_project()
        destination = Path(path)
        ProjectArchive.save(destination, project, self._assets)
        self._path = destination
        return destination

    def close_project(self) -> None:
        self._project = None
        self._path = None
        self._assets = {}

    def replace_assets(self, assets: Mapping[str, bytes]) -> None:
        """Replace embedded assets for future editor milestones.

        Milestone 2C does not expose this method through the GUI, but keeping it
        here avoids teaching later image tools to mutate private session state.
        """

        self.require_project()
        self._assets = {str(path): bytes(content) for path, content in assets.items()}

    def require_project(self) -> Project:
        if self._project is None:
            raise NoActiveProjectError("No project is currently open.")
        return self._project
