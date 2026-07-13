from __future__ import annotations

import json
import warnings
import zipfile
from pathlib import Path

import pytest

import batikcraft_studio.persistence.archive as archive_module
from batikcraft_studio.domain import CanvasSpec, Layer, LayerKind, Project, Transform
from batikcraft_studio.persistence import (
    ArchiveSaveError,
    ArchiveValidationError,
    AssetIntegrityError,
    CorruptArchiveError,
    DuplicateArchiveEntryError,
    MissingAssetError,
    MissingManifestError,
    ProjectArchive,
    UnsafeArchivePathError,
    UnsupportedSchemaVersionError,
)


def _project() -> Project:
    project = Project.create(
        "Flora Otomotif",
        "Balya Rochmadi",
        description="Motif eksperimental dari objek sehari-hari.",
        tags=("Batik", "Kontemporer"),
        canvas=CanvasSpec(width=1600, height=1200, background_color="#efe2c6"),
    )
    project.add_layer(
        Layer(
            name="Mobil Terbatikfikasi",
            kind=LayerKind.BATIKIFIED_OBJECT,
            asset_ref="assets/car.bin",
            opacity=0.75,
            transform=Transform(
                x=125.5,
                y=-30,
                rotation_degrees=18,
                scale_x=0.8,
                scale_y=-0.8,
            ),
            properties={
                "style": "parang_contemporary",
                "seed": 72641,
                "weights": [0.4, 0.35, 0.25],
                "enabled": True,
            },
        )
    )
    return project


def _assets() -> dict[str, bytes]:
    return {
        "assets/car.bin": b"source-object-bytes",
        "masks/car-mask.bin": b"mask-bytes",
        "metadata/generation.json": b'{"seed":72641}',
    }


def _members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path, "r") as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _write_members(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def _manifest(members: dict[str, bytes]) -> dict[str, object]:
    return json.loads(members["project.json"].decode("utf-8"))


def _put_manifest(members: dict[str, bytes], manifest: dict[str, object]) -> None:
    members["project.json"] = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")


def test_save_and_load_round_trip_preserves_domain_and_assets(tmp_path: Path) -> None:
    project = _project()
    destination = tmp_path / "flora-otomotif.batikcraft"

    returned = ProjectArchive.save(destination, project, _assets())
    bundle = ProjectArchive.load(destination)

    assert returned == destination
    assert destination.exists()
    assert project.is_dirty is False
    assert bundle.project.is_dirty is False
    assert bundle.project.project_id == project.project_id
    assert bundle.project.schema_version == project.schema_version
    assert bundle.project.metadata == project.metadata
    assert bundle.project.canvas == project.canvas
    assert bundle.project.active_layer_id == project.active_layer_id
    assert bundle.project.created_at == project.created_at
    assert bundle.project.updated_at == project.updated_at
    assert bundle.project.revision == project.revision
    assert bundle.project.layers == project.layers
    assert dict(bundle.assets) == _assets()
    assert bundle.get_asset("assets/car.bin") == b"source-object-bytes"


def test_loaded_asset_mapping_is_read_only(tmp_path: Path) -> None:
    destination = tmp_path / "readonly.batikcraft"
    ProjectArchive.save(destination, _project(), _assets())
    bundle = ProjectArchive.load(destination)

    with pytest.raises(TypeError):
        bundle.assets["assets/new.bin"] = b"nope"  # type: ignore[index]


def test_save_requires_batikcraft_extension(tmp_path: Path) -> None:
    with pytest.raises(ArchiveValidationError, match="must end"):
        ProjectArchive.save(tmp_path / "project.zip", _project(), _assets())


def test_save_rejects_missing_layer_asset(tmp_path: Path) -> None:
    with pytest.raises(ArchiveValidationError, match="references missing asset"):
        ProjectArchive.save(tmp_path / "missing.batikcraft", _project(), {})


def test_save_rejects_case_insensitive_duplicate_asset_paths(tmp_path: Path) -> None:
    assets = _assets()
    assets["assets/Car.bin"] = b"collision"

    with pytest.raises(DuplicateArchiveEntryError):
        ProjectArchive.save(tmp_path / "duplicate.batikcraft", _project(), assets)


def test_save_rejects_unsafe_and_noncanonical_asset_paths(tmp_path: Path) -> None:
    project = Project.create("Test", "Creator")

    for unsafe_path in (
        "../escape.bin",
        "/assets/absolute.bin",
        "assets\\windows.bin",
        "assets//double.bin",
        "assets/./dot.bin",
        "other/file.bin",
    ):
        with pytest.raises(UnsafeArchivePathError):
            ProjectArchive.save(
                tmp_path / "unsafe.batikcraft",
                project,
                {unsafe_path: b"unsafe"},
            )


def test_save_rejects_non_json_layer_properties(tmp_path: Path) -> None:
    project = Project.create("Test", "Creator")
    project.add_layer(Layer(name="Invalid", properties={"object": object()}))

    with pytest.raises(ArchiveValidationError, match="unsupported value type"):
        ProjectArchive.save(tmp_path / "invalid-properties.batikcraft", project)


def test_atomic_save_failure_preserves_existing_target_and_dirty_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "atomic.batikcraft"
    destination.write_bytes(b"existing-file")
    project = _project()

    def fail_replace(source: object, target: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(archive_module.os, "replace", fail_replace)

    with pytest.raises(ArchiveSaveError, match="simulated replace failure"):
        ProjectArchive.save(destination, project, _assets())

    assert destination.read_bytes() == b"existing-file"
    assert project.is_dirty is True
    assert not list(tmp_path.glob(".atomic.batikcraft.*.tmp"))


def test_load_rejects_non_zip_file(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.batikcraft"
    path.write_bytes(b"not a zip")

    with pytest.raises(CorruptArchiveError):
        ProjectArchive.load(path)


def test_load_rejects_missing_manifest(tmp_path: Path) -> None:
    path = tmp_path / "missing-manifest.batikcraft"
    _write_members(path, {"assets/data.bin": b"data"})

    with pytest.raises(MissingManifestError):
        ProjectArchive.load(path)


def test_load_rejects_path_traversal_member(tmp_path: Path) -> None:
    path = tmp_path / "traversal.batikcraft"
    _write_members(path, {"../escape.bin": b"escape"})

    with pytest.raises(UnsafeArchivePathError):
        ProjectArchive.load(path)


def test_load_rejects_duplicate_archive_entries(tmp_path: Path) -> None:
    valid = tmp_path / "valid.batikcraft"
    ProjectArchive.save(valid, _project(), _assets())
    members = _members(valid)
    path = tmp_path / "duplicate-entry.batikcraft"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.json", members["project.json"])
            archive.writestr("assets/car.bin", members["assets/car.bin"])
            archive.writestr("assets/car.bin", members["assets/car.bin"])

    with pytest.raises(DuplicateArchiveEntryError):
        ProjectArchive.load(path)


def test_load_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "unsupported.batikcraft"
    ProjectArchive.save(path, _project(), _assets())
    members = _members(path)
    manifest = _manifest(members)
    manifest["schema_version"] = "999.0"
    _put_manifest(members, manifest)
    _write_members(path, members)

    with pytest.raises(UnsupportedSchemaVersionError):
        ProjectArchive.load(path)


def test_load_rejects_missing_declared_asset(tmp_path: Path) -> None:
    path = tmp_path / "missing-asset.batikcraft"
    ProjectArchive.save(path, _project(), _assets())
    members = _members(path)
    del members["assets/car.bin"]
    _write_members(path, members)

    with pytest.raises(MissingAssetError):
        ProjectArchive.load(path)


def test_load_rejects_undeclared_file(tmp_path: Path) -> None:
    path = tmp_path / "undeclared.batikcraft"
    ProjectArchive.save(path, _project(), _assets())
    members = _members(path)
    members["assets/unlisted.bin"] = b"not declared"
    _write_members(path, members)

    with pytest.raises(CorruptArchiveError, match="undeclared"):
        ProjectArchive.load(path)


def test_load_rejects_asset_hash_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "hash-mismatch.batikcraft"
    ProjectArchive.save(path, _project(), _assets())
    members = _members(path)
    members["assets/car.bin"] = b"tampered-object-data"
    _write_members(path, members)

    with pytest.raises(AssetIntegrityError):
        ProjectArchive.load(path)


def test_load_rejects_duplicate_manifest_asset_paths(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-manifest.batikcraft"
    ProjectArchive.save(path, _project(), _assets())
    members = _members(path)
    manifest = _manifest(members)
    assets = manifest["assets"]
    assert isinstance(assets, list)
    duplicate = dict(assets[0])
    duplicate["path"] = "assets/Car.bin"
    assets.append(duplicate)
    _put_manifest(members, manifest)
    _write_members(path, members)

    with pytest.raises(ArchiveValidationError, match="Duplicate asset path"):
        ProjectArchive.load(path)


def test_load_rejects_invalid_manifest_fields(tmp_path: Path) -> None:
    path = tmp_path / "invalid-fields.batikcraft"
    ProjectArchive.save(path, _project(), _assets())
    members = _members(path)
    manifest = _manifest(members)
    manifest["unexpected"] = True
    _put_manifest(members, manifest)
    _write_members(path, members)

    with pytest.raises(ArchiveValidationError, match="unexpected"):
        ProjectArchive.load(path)
