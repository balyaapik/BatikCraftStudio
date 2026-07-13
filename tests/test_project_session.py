from __future__ import annotations

from pathlib import Path

import pytest

import batikcraft_studio.application.session as session_module
from batikcraft_studio.application import (
    NoActiveProjectError,
    ProjectPathRequiredError,
    ProjectSession,
)
from batikcraft_studio.domain import Layer
from batikcraft_studio.persistence import ArchiveSaveError, ProjectArchive


def test_empty_session_has_safe_snapshot() -> None:
    session = ProjectSession()

    snapshot = session.snapshot()

    assert snapshot.has_project is False
    assert snapshot.display_path == "Not saved yet"
    assert session.project is None
    assert session.path is None
    assert session.is_dirty is False
    assert dict(session.assets) == {}


def test_new_project_sets_dirty_unsaved_context() -> None:
    session = ProjectSession()

    project = session.new_project(
        title="Flora Otomotif",
        creator="Balya Rochmadi",
        width=1600,
        height=1200,
        background_color="#efe2c6",
    )
    snapshot = session.snapshot()

    assert session.project is project
    assert snapshot.has_project is True
    assert snapshot.title == "Flora Otomotif"
    assert snapshot.creator == "Balya Rochmadi"
    assert snapshot.width == 1600
    assert snapshot.height == 1200
    assert snapshot.background_color == "#EFE2C6"
    assert snapshot.path is None
    assert snapshot.dirty is True


def test_save_requires_path_for_new_project() -> None:
    session = ProjectSession()
    session.new_project(title="Untitled", creator="Creator")

    with pytest.raises(ProjectPathRequiredError):
        session.save()


def test_save_as_updates_path_and_marks_project_clean(tmp_path: Path) -> None:
    session = ProjectSession()
    project = session.new_project(title="Motif", creator="Creator")
    destination = tmp_path / "motif.batikcraft"

    returned = session.save_as(destination)

    assert returned == destination
    assert session.path == destination
    assert destination.exists()
    assert project.is_dirty is False
    assert session.snapshot().display_path == str(destination)


def test_save_reuses_existing_path_after_changes(tmp_path: Path) -> None:
    session = ProjectSession()
    project = session.new_project(title="Motif", creator="Creator")
    destination = tmp_path / "motif.batikcraft"
    session.save_as(destination)
    project.update_metadata(description="Updated")

    returned = session.save()
    loaded = ProjectArchive.load(destination)

    assert returned == destination
    assert project.is_dirty is False
    assert loaded.project.metadata.description == "Updated"


def test_open_project_restores_assets_path_and_clean_state(tmp_path: Path) -> None:
    source_session = ProjectSession()
    source_project = source_session.new_project(title="Motif", creator="Creator")
    source_project.add_layer(Layer(name="Object", asset_ref="assets/object.bin"))
    source_session.replace_assets({"assets/object.bin": b"object-bytes"})
    destination = tmp_path / "motif.batikcraft"
    source_session.save_as(destination)

    session = ProjectSession()
    opened = session.open_project(destination)

    assert opened.metadata.title == "Motif"
    assert session.path == destination
    assert session.is_dirty is False
    assert dict(session.assets) == {"assets/object.bin": b"object-bytes"}
    with pytest.raises(TypeError):
        session.assets["assets/new.bin"] = b"nope"  # type: ignore[index]


def test_open_project_replaces_previous_session_state(tmp_path: Path) -> None:
    stored = ProjectSession()
    stored.new_project(title="Stored", creator="Creator")
    destination = tmp_path / "stored.batikcraft"
    stored.save_as(destination)

    session = ProjectSession()
    session.new_project(title="Temporary", creator="Creator")
    session.replace_assets({"metadata/temp.bin": b"temporary"})

    session.open_project(destination)

    assert session.snapshot().title == "Stored"
    assert session.path == destination
    assert dict(session.assets) == {}


def test_failed_save_as_preserves_existing_session_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = ProjectSession()
    project = session.new_project(title="Motif", creator="Creator")
    original_path = tmp_path / "original.batikcraft"
    session.save_as(original_path)
    project.update_metadata(description="Dirty again")

    def fail_save(*_args: object, **_kwargs: object) -> None:
        raise ArchiveSaveError("simulated failure")

    monkeypatch.setattr(session_module.ProjectArchive, "save", fail_save)

    with pytest.raises(ArchiveSaveError, match="simulated failure"):
        session.save_as(tmp_path / "new-location.batikcraft")

    assert session.path == original_path
    assert project.is_dirty is True


def test_close_project_clears_all_session_state() -> None:
    session = ProjectSession()
    session.new_project(title="Motif", creator="Creator")
    session.replace_assets({"metadata/data.bin": b"data"})

    session.close_project()

    assert session.project is None
    assert session.path is None
    assert dict(session.assets) == {}
    assert session.snapshot().has_project is False


def test_require_project_guards_project_dependent_operations() -> None:
    session = ProjectSession()

    with pytest.raises(NoActiveProjectError):
        session.require_project()
    with pytest.raises(NoActiveProjectError):
        session.replace_assets({})
