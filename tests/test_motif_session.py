from __future__ import annotations

from pathlib import Path

from batikcraft_studio.application import MotifProjectSession
from batikcraft_studio.domain import ObjectKind


def test_cap_motif_creates_complete_object_with_automatic_isen() -> None:
    session = MotifProjectSession()
    project = session.new_project(title="Batik", creator="Perajin", width=600, height=400)

    objects = session.cap_motif(
        "kawung",
        (180, 140),
        ukuran=240,
        warna_motif="#4E2A1E",
        warna_isen="#8B5A2B",
        isi_isen_otomatis=True,
    )

    assert len(objects) == 1
    item = objects[0]
    assert item.kind is ObjectKind.MOTIF
    assert item.asset_ref is not None
    assert item.asset_ref in session.assets
    assert item.properties["motif_role"] == "motif-pokok"
    assert item.properties["motif_label"] == "Kawung"
    assert item.properties["isen_label"] == "Cecek Sawut"
    assert item.properties["isi_isen_otomatis"] is True
    assert len(project.layers) == 1
    assert project.layers[0].objects == objects
    assert project.active_object_id == item.object_id


def test_motif_symmetry_shares_asset_and_undoes_as_one_action() -> None:
    session = MotifProjectSession()
    project = session.new_project(title="Batik", creator="Perajin", width=400, height=400)

    objects = session.cap_motif(
        "truntum",
        (300, 200),
        ukuran=180,
        susun="putar_4",
    )

    assert len(objects) == 4
    assert len({item.asset_ref for item in objects}) == 1
    asset_ref = objects[0].asset_ref
    assert asset_ref is not None
    assert len(project.layers) == 1
    assert len(project.layers[0].objects) == 4

    assert session.undo() is True
    assert session.require_project().layers == ()
    assert asset_ref not in session.assets

    assert session.redo() is True
    assert len(session.require_project().layers) == 1
    assert len(session.require_project().layers[0].objects) == 4
    assert asset_ref in session.assets


def test_motif_can_be_created_without_automatic_isen() -> None:
    session = MotifProjectSession()
    session.new_project(title="Batik", creator="Perajin", width=300, height=300)

    item = session.cap_motif(
        "ceplok",
        (150, 150),
        isi_isen_otomatis=False,
        isen_type="ukel",
    )[0]

    assert item.properties["isi_isen_otomatis"] is False
    assert item.properties["isen_type"] == "ukel"


def test_motif_survives_save_and_reopen(tmp_path: Path) -> None:
    session = MotifProjectSession()
    session.new_project(title="Batik", creator="Perajin", width=500, height=360)
    created = session.cap_motif(
        "lereng",
        (200, 160),
        ukuran=260,
        isen_type="galaran",
        susun="cermin_kiri_kanan",
    )
    path = tmp_path / "motif-pokok.batikcraft"

    session.save_as(path)
    reopened = MotifProjectSession()
    project = reopened.open_project(path)

    assert len(project.layers) == 1
    assert len(project.layers[0].objects) == 2
    first = project.layers[0].objects[0]
    assert first.properties["motif_label"] == "Lereng"
    assert first.properties["isen_label"] == "Galaran"
    assert first.asset_ref == created[0].asset_ref
    assert created[0].asset_ref in reopened.assets
