from __future__ import annotations

import hashlib
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from batikcraft_studio import web_bridge_extensions
from batikcraft_studio.web_bridge import BatikCraftWebClient, BatikCraftWebError


class _Store:
    def load_base_url(self) -> str:
        return "http://127.0.0.1:8000"

    def load_token(self) -> str:
        return "token"


def _client() -> BatikCraftWebClient:
    return BatikCraftWebClient(
        base_url="http://127.0.0.1:8000",
        token="token",
        session_store=_Store(),
    )


def test_marketplace_collections_follow_all_drf_pages() -> None:
    client = _client()
    pages = {
        "nfts/": {
            "results": [{"id": 1}],
            "next": "http://127.0.0.1:8000/api/v1/nfts/?page=2",
        },
        "http://127.0.0.1:8000/api/v1/nfts/?page=2": {
            "results": [{"id": 2}],
            "next": None,
        },
    }

    def request_json(self, method, path, **_kwargs):
        assert method == "GET"
        return pages[path]

    client._request_json = types.MethodType(request_json, client)

    assert client.list_nfts() == [{"id": 1}, {"id": 2}]


def test_pagination_rejects_another_origin() -> None:
    client = _client()

    with pytest.raises(BatikCraftWebError, match="host yang berbeda"):
        client._api_url("https://evil.example/api/v1/nfts/?page=2")


def test_capabilities_request_does_not_require_existing_token() -> None:
    client = _client()
    observed = {}

    def request_json(self, method, path, **kwargs):
        observed.update(method=method, path=path, kwargs=kwargs)
        return {"api_version": "1.1"}

    client._request_json = types.MethodType(request_json, client)

    assert client.capabilities()["api_version"] == "1.1"
    assert observed == {
        "method": "GET",
        "path": "capabilities/",
        "kwargs": {"authenticated": False},
    }


def test_publish_nft_sends_preview_and_original_package(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "motif.batikcraftnft"
    source.write_bytes(b"source-package")
    bundle = SimpleNamespace(
        manifest={
            "identity": {"title": "Motif Sekar"},
            "artwork": {"motifs": ["sekar"], "license": "personal"},
        },
        project=SimpleNamespace(
            project_id="project-sekar",
            metadata=SimpleNamespace(title="Motif Sekar"),
        ),
        package_id="package-sekar",
        preview_jpeg=b"jpeg-preview",
    )
    monkeypatch.setattr(web_bridge_extensions, "load_batikcraft_nft", lambda _path: bundle)

    client = _client()
    observed = {}

    def request_multipart(self, method, path, *, fields, files):
        observed.update(method=method, path=path, fields=fields, files=files)
        return {"id": 42}

    def request_json(self, method, path, **kwargs):
        observed["publish"] = (method, path, kwargs)
        return {"id": 42, "status": "listed"}

    client._request_multipart = types.MethodType(request_multipart, client)
    client._request_json = types.MethodType(request_json, client)

    result = client.publish_nft_package(source, starting_price="125000")

    assert result["status"] == "listed"
    assert observed["path"] == "nfts/"
    assert observed["files"]["image"][1] == b"jpeg-preview"
    assert observed["files"]["package_file"][0] == "motif.batikcraftnft"
    assert observed["files"]["package_file"][1] == b"source-package"
    assert observed["publish"] == (
        "POST",
        "nfts/42/publish/",
        {"payload": {}},
    )


def test_download_nft_package_checks_server_sha256(tmp_path: Path) -> None:
    client = _client()
    content = b"verified-batik-package"
    checksum = hashlib.sha256(content).hexdigest()

    def request_bytes(self, method, path):
        assert (method, path) == ("GET", "nfts/7/package/")
        return content, {
            "Content-Disposition": 'attachment; filename="sekar.batikpack"',
            "X-BatikCraft-Package-SHA256": checksum,
        }

    client._request_bytes = types.MethodType(request_bytes, client)
    output = client.download_nft_package(7, tmp_path)

    assert output.name == "sekar.batikpack"
    assert output.read_bytes() == content


def test_download_nft_package_rejects_bad_checksum(tmp_path: Path) -> None:
    client = _client()

    def request_bytes(self, method, path):
        return b"corrupt", {
            "Content-Disposition": 'attachment; filename="bad.batikpack"',
            "X-BatikCraft-Package-SHA256": "0" * 64,
        }

    client._request_bytes = types.MethodType(request_bytes, client)

    with pytest.raises(BatikCraftWebError, match="Checksum"):
        client.download_nft_package(8, tmp_path)
