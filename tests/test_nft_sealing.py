"""Paket bersegel yang dihasilkan Studio harus lolos aturan BatikCraftWeb.

Web menolak gambar NFT yang tidak datang bersama paket .batikcraftnft bersegel
dan yang sidik jarinya tidak sama dengan preview.jpg di dalam paket. Test ini
memeriksa invarian yang sama dari sisi Studio, supaya ketidakcocokan ketahuan di
sini alih-alih baru muncul sebagai penolakan server.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest
from PIL import Image

from batikcraft_studio.nft_sealing import SealingError, seal_image_as_nft_package


def _png(size=(32, 24), color=(180, 90, 30)) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", size, color).save(stream, format="PNG")
    return stream.getvalue()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sealed(**overrides):
    params = {
        "title": "Sekar Jagad",
        "creator_name": "Creator Uji",
        "creator_user_id": "42",
        "description": "Motif untuk pengujian.",
    }
    params.update(overrides)
    return seal_image_as_nft_package(_png(), **params)


def test_sealed_package_contains_manifest_seal_and_preview() -> None:
    sealed = _sealed()

    with zipfile.ZipFile(io.BytesIO(sealed.package_bytes)) as archive:
        names = set(archive.namelist())

    assert "manifest.json" in names
    assert "seal.json" in names
    assert "preview.jpg" in names


def test_uploaded_preview_matches_the_hash_declared_in_manifest() -> None:
    """Inilah pemeriksaan inti yang dilakukan server."""
    sealed = _sealed()

    with zipfile.ZipFile(io.BytesIO(sealed.package_bytes)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        declared = {entry["path"]: entry for entry in manifest["files"]}

    assert declared["preview.jpg"]["sha256"] == _sha256(sealed.preview_jpeg)
    assert declared["preview.jpg"]["size"] == len(sealed.preview_jpeg)


def test_seal_matches_manifest_digest() -> None:
    sealed = _sealed()

    with zipfile.ZipFile(io.BytesIO(sealed.package_bytes)) as archive:
        manifest_bytes = archive.read("manifest.json")
        seal = json.loads(archive.read("seal.json"))

    assert seal["manifest_sha256"] == _sha256(manifest_bytes)
    assert seal["package_id"] == json.loads(manifest_bytes)["package_id"]


def test_every_declared_file_matches_its_checksum() -> None:
    sealed = _sealed()

    with zipfile.ZipFile(io.BytesIO(sealed.package_bytes)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for entry in manifest["files"]:
            content = archive.read(entry["path"])
            assert len(content) == entry["size"]
            assert _sha256(content) == entry["sha256"]


def test_manifest_declares_the_expected_format() -> None:
    sealed = _sealed()

    with zipfile.ZipFile(io.BytesIO(sealed.package_bytes)) as archive:
        manifest = json.loads(archive.read("manifest.json"))

    assert manifest["format"] == "batikcraft-nft"
    assert manifest["identity"]["creator"]["user_id"] == "42"
    assert manifest["identity"]["title"] == "Sekar Jagad"


def test_preview_is_jpeg_regardless_of_source_format() -> None:
    sealed = _sealed()

    with Image.open(io.BytesIO(sealed.preview_jpeg)) as preview:
        assert preview.format == "JPEG"


def test_blank_title_is_rejected() -> None:
    with pytest.raises(SealingError):
        _sealed(title="   ")


def test_empty_image_is_rejected() -> None:
    with pytest.raises(SealingError):
        seal_image_as_nft_package(
            b"",
            title="Sekar",
            creator_name="Creator",
            creator_user_id="1",
        )


def test_unreadable_image_is_rejected() -> None:
    with pytest.raises(SealingError):
        seal_image_as_nft_package(
            b"ini bukan gambar",
            title="Sekar",
            creator_name="Creator",
            creator_user_id="1",
        )


def test_oversized_image_is_scaled_down_for_preview() -> None:
    sealed = seal_image_as_nft_package(
        _png(size=(5000, 200)),
        title="Panjang",
        creator_name="Creator",
        creator_user_id="1",
    )

    with Image.open(io.BytesIO(sealed.preview_jpeg)) as preview:
        assert max(preview.size) <= 4096


def test_package_filename_is_slugified() -> None:
    sealed = _sealed(title="Sekar Jagad / Mega Mendung")

    assert sealed.package_filename.endswith(".batikcraftnft")
    assert " " not in sealed.package_filename
    assert "/" not in sealed.package_filename
