from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from batikcraft_studio.domain import CanvasSpec, Project
from batikcraft_studio.persistence import (
    BatikNFTIntegrityError,
    NFTExportMetadata,
    export_batikcraft_nft,
    load_batikcraft_nft,
)


def _project() -> Project:
    return Project.create(
        "Parang Masa Depan",
        "Balya Rochmadi",
        description="Keseimbangan tradisi dan teknologi.",
        tags=("Parang", "Kontemporer"),
        canvas=CanvasSpec(width=64, height=48, background_color="#F4E6C8"),
    )


def _preview() -> bytes:
    output = BytesIO()
    Image.new("RGB", (64, 48), "#8B4513").save(output, format="JPEG", quality=90)
    return output.getvalue()


def _metadata() -> NFTExportMetadata:
    return NFTExportMetadata(
        creator_user_id="balya-rochmadi",
        philosophy="Parang melambangkan kesinambungan perjuangan dan tanggung jawab.",
        motifs=("Parang", "Isen Cecek"),
        colors=("#8B4513", "#F4E6C8"),
        license_name="All rights reserved",
    )


def _members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path, "r") as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _write_members(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_nft_round_trip_preserves_identity_project_and_preview(tmp_path: Path) -> None:
    project = _project()
    destination = tmp_path / "parang.batikcraftnft"

    returned = export_batikcraft_nft(
        destination,
        project,
        {},
        _preview(),
        _metadata(),
    )
    bundle = load_batikcraft_nft(destination)

    assert returned == destination
    assert project.is_dirty is True
    assert bundle.project.project_id == project.project_id
    assert bundle.project.metadata == project.metadata
    assert bundle.preview_jpeg == _preview()
    assert bundle.manifest["identity"]["creator"] == {
        "display_name": "Balya Rochmadi",
        "user_id": "balya-rochmadi",
    }
    assert len(bundle.package_id) == 64


def test_tampered_preview_invalidates_nft_checksum(tmp_path: Path) -> None:
    destination = tmp_path / "tampered.batikcraftnft"
    export_batikcraft_nft(destination, _project(), {}, _preview(), _metadata())
    members = _members(destination)
    members["preview.jpg"] = members["preview.jpg"] + b"tamper"
    _write_members(destination, members)

    with pytest.raises(BatikNFTIntegrityError, match="Checksum"):
        load_batikcraft_nft(destination)


def test_changed_identity_without_new_seal_is_rejected(tmp_path: Path) -> None:
    destination = tmp_path / "identity.batikcraftnft"
    export_batikcraft_nft(destination, _project(), {}, _preview(), _metadata())
    members = _members(destination)
    manifest = json.loads(members["manifest.json"].decode("utf-8"))
    manifest["identity"]["creator"]["display_name"] = "Nama Lain"
    members["manifest.json"] = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    _write_members(destination, members)

    with pytest.raises(BatikNFTIntegrityError, match="Seal"):
        load_batikcraft_nft(destination)


def test_export_requires_batikcraftnft_extension(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="batikcraftnft"):
        export_batikcraft_nft(
            tmp_path / "wrong.zip",
            _project(),
            {},
            _preview(),
            _metadata(),
        )
