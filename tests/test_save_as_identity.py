"""Save As menghasilkan karya berdiri sendiri agar dapat diunggah terpisah."""

from __future__ import annotations

from pathlib import Path

from batikcraft_studio.application import ProjectSession
from batikcraft_studio.persistence import ProjectArchive


def _session(tmp_path: Path, title: str = "Karya") -> tuple[ProjectSession, object]:
    session = ProjectSession()
    project = session.new_project(title=title, creator="Balya", width=200, height=200)
    return session, project


def test_save_as_gives_the_copy_a_new_project_id(tmp_path: Path) -> None:
    """Regresi: dua berkas hasil Save As berbagi project_id, sehingga
    BatikCraftWeb menolak unggahan kedua sebagai duplikat."""

    session, project = _session(tmp_path)
    session.save_as(tmp_path / "versi-1.batikcraft")
    first_id = project.project_id

    session.save_as(tmp_path / "versi-2.batikcraft")

    assert project.project_id != first_id
    stored_first = ProjectArchive.load(tmp_path / "versi-1.batikcraft").project
    stored_second = ProjectArchive.load(tmp_path / "versi-2.batikcraft").project
    assert stored_first.project_id != stored_second.project_id


def test_custom_title_is_preserved(tmp_path: Path) -> None:
    session, project = _session(tmp_path, title="Batik Parang Klithik")
    session.save_as(tmp_path / "parang-v1.batikcraft")

    session.save_as(tmp_path / "parang-v2.batikcraft")

    assert project.metadata.title == "Batik Parang Klithik"


def test_title_following_the_filename_is_updated(tmp_path: Path) -> None:
    """Judul yang hanya mengikuti nama berkas ikut menyesuaikan."""

    session, project = _session(tmp_path, title="karya-a")
    session.save_as(tmp_path / "karya-a.batikcraft")

    session.save_as(tmp_path / "karya-b.batikcraft")

    assert project.metadata.title == "karya-b"


def test_first_save_changes_nothing(tmp_path: Path) -> None:
    session, project = _session(tmp_path, title="Motif")
    original_id = project.project_id

    session.save_as(tmp_path / "motif.batikcraft")

    assert project.metadata.title == "Motif"
    assert project.project_id == original_id


def test_saving_over_the_same_path_keeps_identity(tmp_path: Path) -> None:
    session, project = _session(tmp_path, title="Motif")
    destination = tmp_path / "motif.batikcraft"
    session.save_as(destination)
    identity = project.project_id

    session.save_as(destination)

    assert project.project_id == identity


def test_new_identity_can_be_disabled(tmp_path: Path) -> None:
    session, project = _session(tmp_path, title="Motif")
    session.save_as(tmp_path / "a.batikcraft")
    identity = project.project_id

    session.save_as(tmp_path / "b.batikcraft", new_identity=False)

    assert project.project_id == identity
