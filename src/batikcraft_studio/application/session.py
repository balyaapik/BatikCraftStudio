"""Project-session service used by the Tkinter shell and layer editor."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

from batikcraft_studio.domain import CanvasSpec, Layer, LayerKind, Project, Transform
from batikcraft_studio.imaging import RasterAsset, normalize_raster_image
from batikcraft_studio.persistence import ProjectArchive

HISTORY_LIMIT = 100


class ProjectSessionError(RuntimeError):
    """Base class for project-session failures."""


class NoActiveProjectError(ProjectSessionError):
    """Raised when an operation requires an active project."""


class ProjectPathRequiredError(ProjectSessionError):
    """Raised when Save is requested before a project has a file path."""


class LayerLockedError(ProjectSessionError):
    """Raised when an editing command targets a locked layer."""


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
    active_layer_id: str | None = None
    can_undo: bool = False
    can_redo: bool = False

    @property
    def display_path(self) -> str:
        return str(self.path) if self.path is not None else "Not saved yet"


@dataclass(frozen=True, slots=True)
class _SessionState:
    project: Project | None
    path: Path | None
    assets: tuple[tuple[str, bytes], ...]


class ProjectSession:
    """Coordinate the active project, archive path, assets, and editor history."""

    def __init__(self) -> None:
        self._project: Project | None = None
        self._path: Path | None = None
        self._assets: dict[str, bytes] = {}
        self._undo_stack: list[_SessionState] = []
        self._redo_stack: list[_SessionState] = []

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

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def snapshot(self) -> ProjectSessionSnapshot:
        project = self._project
        if project is None:
            return ProjectSessionSnapshot(
                has_project=False,
                can_undo=self.can_undo,
                can_redo=self.can_redo,
            )
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
            active_layer_id=project.active_layer_id,
            can_undo=self.can_undo,
            can_redo=self.can_redo,
        )

    def new_project(
        self,
        *,
        title: str,
        creator: str,
        width: int = 2048,
        height: int = 2048,
        background_color: str = "#FFFFFF",
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
        self._clear_history()
        return project

    def open_project(self, path: str | Path) -> Project:
        archive_path = Path(path)
        bundle = ProjectArchive.load(archive_path)
        self._project = bundle.project
        self._path = archive_path
        self._assets = dict(bundle.assets)
        self._clear_history()
        return bundle.project

    def save(self) -> Path:
        project = self.require_project()
        if self._path is None:
            raise ProjectPathRequiredError("Use Save As before saving this project.")
        ProjectArchive.save(self._path, project, self._assets)
        return self._path

    def save_as(self, path: str | Path, *, new_identity: bool = True) -> Path:
        """Simpan ke berkas lain sebagai karya yang berdiri sendiri.

        Menyimpan proyek yang SUDAH pernah tersimpan ke nama berkas lain
        menghasilkan karya baru: project_id diperbarui agar dua berkas tidak
        berbagi identitas (penyebab unggahan ke BatikCraftWeb ditolak sebagai
        duplikat). Judul hanya ikut berubah bila memang mengikuti nama berkas
        lama atau masih kosong — judul yang sengaja ditulis pengguna
        dipertahankan.
        """

        project = self.require_project()
        destination = Path(path)
        previous = self._path
        is_copy = (
            new_identity
            and previous is not None
            and previous.resolve() != destination.resolve()
        )
        if is_copy:
            project.adopt_new_identity(
                title=self._derived_title(project.metadata.title, previous, destination)
            )
        ProjectArchive.save(destination, project, self._assets)
        self._path = destination
        return destination

    @staticmethod
    def _derived_title(
        current: str,
        previous: Path,
        destination: Path,
    ) -> str | None:
        """Judul baru bila judul lama hanya mengikuti nama berkas, else None."""

        cleaned = str(current).strip()
        placeholder = cleaned.casefold() in {"", "untitled", "tanpa judul"}
        follows_filename = cleaned.casefold() == previous.stem.casefold()
        if placeholder or follows_filename:
            return destination.stem
        return None

    def close_project(self) -> None:
        self._project = None
        self._path = None
        self._assets = {}
        self._clear_history()

    def replace_assets(self, assets: Mapping[str, bytes]) -> None:
        """Replace embedded assets for compatibility and non-editor workflows."""

        self.require_project()
        self._assets = {str(path): bytes(content) for path, content in assets.items()}

    def import_raster_image(
        self,
        filename: str,
        content: bytes | bytearray | memoryview,
    ) -> Layer:
        """Normalize image bytes and add a centered editable raster layer."""

        project = self.require_project()
        raster = normalize_raster_image(content)
        asset_ref = f"assets/{uuid4()}.png"
        scale = _initial_import_scale(project, raster)
        stem = Path(filename).stem.strip() or "Imported image"
        layer = Layer(
            name=stem[:120],
            kind=LayerKind.RASTER,
            asset_ref=asset_ref,
            transform=Transform(
                x=project.canvas.width / 2,
                y=project.canvas.height / 2,
                scale_x=scale,
                scale_y=scale,
            ),
            properties={
                "pixel_width": raster.width,
                "pixel_height": raster.height,
                "source_format": raster.source_format,
                "original_name": Path(filename).name,
            },
        )

        def mutation() -> None:
            self._assets[asset_ref] = raster.content
            project.add_layer(layer)

        self._commit_mutation(mutation)
        return layer

    def select_layer(self, layer_id: str | None) -> None:
        self.require_project().set_active_layer(layer_id)

    def update_layer_transform(
        self,
        layer_id: str,
        *,
        x: float | None = None,
        y: float | None = None,
        rotation_degrees: float | None = None,
        scale_x: float | None = None,
        scale_y: float | None = None,
    ) -> Layer:
        project = self.require_project()
        layer = self._require_unlocked_layer(layer_id)
        current = layer.transform
        candidate = Transform(
            x=current.x if x is None else x,
            y=current.y if y is None else y,
            rotation_degrees=(
                current.rotation_degrees
                if rotation_degrees is None
                else rotation_degrees
            ),
            scale_x=current.scale_x if scale_x is None else scale_x,
            scale_y=current.scale_y if scale_y is None else scale_y,
        )
        if candidate == current:
            return layer

        updated: Layer | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_layer(layer_id, transform=candidate)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Layer transform update did not produce a result.")
        return updated

    def move_layer(self, layer_id: str, *, x: float, y: float) -> Layer:
        return self.update_layer_transform(layer_id, x=x, y=y)

    def set_layer_opacity(self, layer_id: str, opacity: float) -> Layer:
        project = self.require_project()
        layer = self._require_unlocked_layer(layer_id)
        if float(opacity) == layer.opacity:
            return layer
        updated: Layer | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_layer(layer_id, opacity=opacity)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Layer opacity update did not produce a result.")
        return updated

    def duplicate_layer(self, layer_id: str) -> Layer:
        project = self.require_project()
        source = project.get_layer(layer_id)
        duplicate = Layer(
            name=_copy_name(source.name),
            kind=source.kind,
            asset_ref=source.asset_ref,
            visible=source.visible,
            locked=False,
            opacity=source.opacity,
            transform=replace(
                source.transform,
                x=source.transform.x + 24,
                y=source.transform.y + 24,
            ),
            properties=dict(source.properties),
        )
        source_index = next(
            index for index, item in enumerate(project.layers) if item.layer_id == layer_id
        )
        self._commit_mutation(
            lambda: project.add_layer(duplicate, index=source_index + 1, select=True)
        )
        return duplicate

    def delete_layer(self, layer_id: str) -> Layer:
        project = self.require_project()
        layer = self._require_unlocked_layer(layer_id)
        removed: Layer | None = None

        def mutation() -> None:
            nonlocal removed
            removed = project.remove_layer(layer_id)
            if layer.asset_ref is not None and not any(
                item.asset_ref == layer.asset_ref for item in project.layers
            ):
                self._assets.pop(layer.asset_ref, None)

        self._commit_mutation(mutation)
        if removed is None:
            raise ProjectSessionError("Layer deletion did not produce a result.")
        return removed

    def set_layer_visibility(self, layer_id: str, visible: bool) -> Layer:
        project = self.require_project()
        layer = project.get_layer(layer_id)
        if layer.visible == visible:
            return layer
        updated: Layer | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_layer(layer_id, visible=visible)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Layer visibility update did not produce a result.")
        return updated

    def set_layer_locked(self, layer_id: str, locked: bool) -> Layer:
        project = self.require_project()
        layer = project.get_layer(layer_id)
        if layer.locked == locked:
            return layer
        updated: Layer | None = None

        def mutation() -> None:
            nonlocal updated
            updated = project.update_layer(layer_id, locked=locked)

        self._commit_mutation(mutation)
        if updated is None:
            raise ProjectSessionError("Layer lock update did not produce a result.")
        return updated

    def reorder_layer(self, layer_id: str, new_index: int) -> None:
        project = self.require_project()
        current_index = next(
            index for index, item in enumerate(project.layers) if item.layer_id == layer_id
        )
        if current_index == new_index:
            return
        self._commit_mutation(lambda: project.reorder_layer(layer_id, new_index))

    def move_layer_up(self, layer_id: str) -> bool:
        project = self.require_project()
        index = next(index for index, item in enumerate(project.layers) if item.layer_id == layer_id)
        if index >= len(project.layers) - 1:
            return False
        self.reorder_layer(layer_id, index + 1)
        return True

    def move_layer_down(self, layer_id: str) -> bool:
        project = self.require_project()
        index = next(index for index, item in enumerate(project.layers) if item.layer_id == layer_id)
        if index <= 0:
            return False
        self.reorder_layer(layer_id, index - 1)
        return True

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        current = self._capture_state()
        target = self._undo_stack.pop()
        self._redo_stack.append(current)
        self._restore_state(target)
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        current = self._capture_state()
        target = self._redo_stack.pop()
        self._append_history(self._undo_stack, current)
        self._restore_state(target)
        return True

    def require_project(self) -> Project:
        if self._project is None:
            raise NoActiveProjectError("No project is currently open.")
        return self._project

    def _require_unlocked_layer(self, layer_id: str) -> Layer:
        layer = self.require_project().get_layer(layer_id)
        if layer.locked:
            raise LayerLockedError(f"Layer {layer.name!r} is locked.")
        return layer

    def _commit_mutation(self, mutation: Callable[[], None]) -> None:
        before = self._capture_state()
        try:
            mutation()
        except Exception:
            self._restore_state(before)
            raise
        self._append_history(self._undo_stack, before)
        self._redo_stack.clear()

    def _capture_state(self) -> _SessionState:
        return _SessionState(
            project=_clone_project(self._project),
            path=self._path,
            assets=tuple(sorted(self._assets.items())),
        )

    def _restore_state(self, state: _SessionState) -> None:
        self._project = _clone_project(state.project)
        self._path = state.path
        self._assets = dict(state.assets)

    def _clear_history(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        # Bitmap hidup lapis canting milik proyek yang ditinggalkan; lepaskan
        # agar proyek baru tidak memakai gambar basi.
        try:
            from batikcraft_studio.imaging import live_bitmap_store

            live_bitmap_store.clear()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _append_history(stack: list[_SessionState], state: _SessionState) -> None:
        stack.append(state)
        if len(stack) > HISTORY_LIMIT:
            del stack[0]


def _clone_project(project: Project | None) -> Project | None:
    if project is None:
        return None
    return Project(
        metadata=project.metadata,
        canvas=project.canvas,
        layers=project.layers,
        project_id=project.project_id,
        schema_version=project.schema_version,
        active_layer_id=project.active_layer_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        revision=project.revision,
        saved_revision=project.saved_revision,
    )


def _initial_import_scale(project: Project, raster: RasterAsset) -> float:
    return min(
        1.0,
        project.canvas.width * 0.65 / raster.width,
        project.canvas.height * 0.65 / raster.height,
    )


def _copy_name(name: str) -> str:
    suffix = " copy"
    maximum_base = max(1, 120 - len(suffix))
    return f"{name[:maximum_base].rstrip()}{suffix}"
