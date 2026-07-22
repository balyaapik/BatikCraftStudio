"""Publikasi NFT dari gambar rata dokumen raster (bukan paket objek)."""

from __future__ import annotations

import pytest

from batikcraft_studio.web_bridge import BatikCraftWebClient, BatikCraftWebError, _slugify


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

    def _json(method, path, *, payload):
        captured["publish"] = path
        return {"id": 42, "status": "published"}

    client._request_multipart = _mp  # type: ignore[method-assign]
    client._request_json = _json  # type: ignore[method-assign]
    return client, captured


def test_publish_image_nft_plumbing():
    client, captured = _client_with_capture()

    result = client.publish_image_nft(
        b"\x89PNGdata", title="Kawung", description="filosofi", starting_price="0.5"
    )

    assert result["status"] == "published"
    assert captured["fields"]["title"] == "Kawung"
    assert captured["fields"]["starting_price"] == "0.5"
    assert captured["files"]["image"][0] == "kawung.png"
    assert captured["files"]["image"][2] == "image/png"
    assert captured["publish"] == "nfts/42/publish/"


def test_judul_kosong_ditolak():
    client, _ = _client_with_capture()
    with pytest.raises(BatikCraftWebError):
        client.publish_image_nft(b"x", title="   ")


def test_gambar_kosong_ditolak():
    client, _ = _client_with_capture()
    with pytest.raises(BatikCraftWebError):
        client.publish_image_nft(b"", title="Motif")
