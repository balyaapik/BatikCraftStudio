from __future__ import annotations

from pathlib import Path

from batikcraft_studio.application import MotifProjectSession
from batikcraft_studio.domain import LayerKind


def test_cap_motif_creates_complete_batik_layer_with_automatic_isen() -> None:
    session = MotifProjectSession()
    project = session.new_project(title="Batik", creator="Perajin", width=600, height=400)

    layers = session.cap_motif(
        "kawung",
        (180, 140),
        ukuran=240,
        warna_motif="#4E2A1E",
        warna_isen="#8B5A2B",
        isi_isen_otomatis=True,
    )

    assert len(layers) == 1
    layer = layers[0]
    assert layer.kind is LayerKind.RASTER
    assert layer.asset_ref is not None
    assert layer.asset_ref in session.assets
    assert layer.properties["motif_role"] == "motif-pokok"
    assert layer.properties["motif_label"] == "Kawung"
    assert layer.properties["isen_label"] == "Cecek Sawut"
    assert layer.properties["isi_isen_otomatis"] is True
    assert project.active_layer_id == layer.layer_id


def test_motif_symmetry_shares_asset_and_undoes_as_one_action() -> None:
    session = MotifProjectSession()
    project = session.new_project(title="Batik", creator="Perajin", width=400, height=400)

    layers = session.cap_motif(
        "truntum",
        (300, 200),
        ukuran=180,
        susun="putar_4",
    )

    assert len(layers) == 4
    assert len({layer.asset_ref for layer in layers}) == 1
    asset_ref = layers[0].asset_ref
    assert asset_ref is not None
    assert len(project.layers) == 4

    assert session.undo() is True
    assert len(session.require_project().layers) == 0
    assert asset_ref not in session.assets

    assert session.redo() is True
    assert len(session.require_project().layers) == 4
    assert asset_ref in session.assets


def test_motif_can_be_created_without_automatic_isen() -> None:
    session = MotifProjectSession()
    session.new_project(title="Batik", creator="Perajin", width=300, height=300)

    layer = session.cap_motif(
        "ceplok",
        (150, 150),
        isi_isen_otomatis=False,
        isen_type="ukel",
    )[0]

    assert layer.properties["isi_isen_otomatis"] is False
    assert layer.properties["isen_type"] == "ukel"


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

    assert len(project.layers) == 2
    assert project.layers[0].properties["motif_label"] == "Lereng"
    assert project.layers[0].properties["isen_label"] == "Galaran"
    assert project.layers[0].asset_ref == created[0].asset_ref
    assert created[0].asset_ref in reopened.assets
