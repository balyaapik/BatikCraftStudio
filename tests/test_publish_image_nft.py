"""Publikasi NFT dari gambar rata dokumen raster (bukan paket objek)."""

from __future__ import annotations

import pytest

from batikcraft_studio.web_bridge import (
    BatikCraftWebClient,
    BatikCraftWebError,
    _slugify,
)


def _png_bytes() -> bytes:
    """Gambar sungguhan: jalur publish kini menyegelnya menjadi paket."""
    import io

    from PIL import Image

    stream = io.BytesIO()
    Image.new("RGB", (8, 8), (120, 60, 20)).save(stream, format="PNG")
    return stream.getvalue()


def test_slugify():
    assert _slugify("Kawung Klasik!") == "kawung-klasik"
    assert _slugify("") == "motif"
    assert _slugify("A" * 100) == "a" * 60


def _client_with_capture():
    client = BatikCraftWebClient.__new__(BatikCraftWebClient)
    captured: dict = {}

    def _mp(method, path, *, fields, files):
        captured["path"] = path
        captured["fields"] = fields
        captured["files"] = files
        return {"id": 42}

    def _json(method, path, *, payload=None, **kwargs):
        if path == "me/":
            return {
                "id": 7,
                "username": "creator",
                "public_name": "Creator Uji",
                "email": "creator@contoh.test",
                "role": "creator",
            }
        captured["publish"] = path
        return {"id": 42, "status": "published"}

    client._request_multipart = _mp  # type: ignore[method-assign]
    client._request_json = _json  # type: ignore[method-assign]
    return client, captured


def test_publish_image_nft_plumbing():
    client, captured = _client_with_capture()

    result = client.publish_image_nft(
        _png_bytes(), title="Kawung", description="filosofi", starting_price="0.5"
    )

    assert result["status"] == "published"
    assert captured["fields"]["title"] == "Kawung"
    assert captured["fields"]["starting_price"] == "0.5"
    # Server hanya menerima gambar bersama paket bersegel, dan previewnya JPEG.
    assert captured["files"]["image"][0] == "preview.jpg"
    assert captured["files"]["image"][2] == "image/jpeg"
    assert captured["files"]["package_file"][0].endswith(".batikcraftnft")
    assert captured["publish"] == "nfts/42/publish/"


def test_publish_image_nft_sends_a_package_whose_preview_matches_the_image():
    """Sidik jari gambar wajib sama dengan preview di dalam paket."""
    import hashlib
    import io
    import json
    import zipfile

    client, captured = _client_with_capture()

    client.publish_image_nft(_png_bytes(), title="Kawung", starting_price="1")

    image_bytes = captured["files"]["image"][1]
    package_bytes = captured["files"]["package_file"][1]
    with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    declared = {entry["path"]: entry for entry in manifest["files"]}

    assert declared["preview.jpg"]["sha256"] == hashlib.sha256(image_bytes).hexdigest()


def test_judul_kosong_ditolak():
    client, _ = _client_with_capture()
    with pytest.raises(BatikCraftWebError):
        client.publish_image_nft(_png_bytes(), title="   ")


def test_gambar_kosong_ditolak():
    client, _ = _client_with_capture()
    with pytest.raises(BatikCraftWebError):
        client.publish_image_nft(b"", title="Motif")
