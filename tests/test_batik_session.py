from __future__ import annotations

from pathlib import Path

import pytest

from batikcraft_studio.application import BatikProjectSession, CapIsenError
from batikcraft_studio.domain import LayerKind


def test_cap_isen_creates_raster_layer_with_batik_metadata() -> None:
    session = BatikProjectSession()
    project = session.new_project(title="Batik", creator="Perajin", width=400, height=300)

    layers = session.cap_isen(
        "cecek",
        (120, 90),
        ukuran=64,
        warna="#8B5A2B",
        susun="tunggal",
    )

    assert len(layers) == 1
    layer = layers[0]
    assert layer.kind is LayerKind.RASTER
    assert layer.asset_ref is not None
    assert layer.asset_ref in session.assets
    assert layer.transform.x == 120
    assert layer.transform.y == 90
    assert layer.transform.scale_x == pytest.approx(0.25)
    assert layer.properties["motif_role"] == "isen-isen"
    assert layer.properties["isen_label"] == "Cecek"
    assert layer.properties["warna_isen"] == "#8B5A2B"
    assert project.active_layer_id == layer.layer_id


def test_cermin_empat_shares_one_asset_and_one_history_step() -> None:
    session = BatikProjectSession()
    project = session.new_project(title="Batik", creator="Perajin", width=300, height=200)

    layers = session.cap_isen(
        "ukel",
        (60, 50),
        ukuran=80,
        warna="#243B66",
        susun="cermin_empat",
    )

    assert len(layers) == 4
    assert len({layer.asset_ref for layer in layers}) == 1
    asset_ref = layers[0].asset_ref
    assert asset_ref is not None
    assert asset_ref in session.assets
    assert len(project.layers) == 4

    assert session.undo() is True
    assert len(session.require_project().layers) == 0
    assert asset_ref not in session.assets

    assert session.redo() is True
    assert len(session.require_project().layers) == 4
    assert asset_ref in session.assets


def test_putar_4_records_rotation_and_susun_metadata() -> None:
    session = BatikProjectSession()
    session.new_project(title="Batik", creator="Perajin", width=200, height=200)

    layers = session.cap_isen(
        "sawut",
        (150, 100),
        ukuran=48,
        susun="putar_4",
    )

    assert [layer.transform.rotation_degrees for layer in layers] == [0, 90, 180, 270]
    assert [layer.properties["susun_index"] for layer in layers] == [1, 2, 3, 4]
    assert all(layer.properties["pola_susun"] == "putar_4" for layer in layers)


def test_cap_isen_survives_save_and_reopen(tmp_path: Path) -> None:
    session = BatikProjectSession()
    session.new_project(title="Batik", creator="Perajin", width=240, height=180)
    created = session.cap_isen(
        "cecek_sawut",
        (80, 70),
        ukuran=96,
        warna="#8F3D36",
        susun="cermin_kiri_kanan",
    )
    path = tmp_path / "isen.batikcraft"

    session.save_as(path)
    reopened = BatikProjectSession()
    project = reopened.open_project(path)

    assert len(project.layers) == 2
    assert project.layers[0].properties["isen_label"] == "Cecek Sawut"
    assert project.layers[0].asset_ref == created[0].asset_ref
    assert created[0].asset_ref in reopened.assets


def test_cap_isen_rejects_invalid_size_without_mutating_project() -> None:
    session = BatikProjectSession()
    project = session.new_project(title="Batik", creator="Perajin", width=200, height=200)

    with pytest.raises(CapIsenError, match="antara 8 dan 1024"):
        session.cap_isen("cecek", (100, 100), ukuran=2)

    assert len(project.layers) == 0
    assert dict(session.assets) == {}
