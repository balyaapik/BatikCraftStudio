"""Compatibility extensions for the complete BatikCraftWeb Studio API contract."""

from __future__ import annotations

import json
import mimetypes
import urllib.parse
from pathlib import Path
from typing import Any

from batikcraft_studio.config import APP_VERSION
from batikcraft_studio.persistence.nft_package import load_batikcraft_nft

from . import web_bridge

_INSTALLED = False
_ORIGINAL_API_URL = web_bridge.BatikCraftWebClient._api_url


def install_web_bridge_extensions() -> None:
    """Add pagination, capabilities, and NFT package transfer support once."""

    global _INSTALLED
    if _INSTALLED:
        return

    client = web_bridge.BatikCraftWebClient
    client._api_url = _api_url  # type: ignore[method-assign]
    client._request_collection = _request_collection  # type: ignore[attr-defined]
    client.capabilities = capabilities  # type: ignore[attr-defined]
    client.list_nfts = list_nfts  # type: ignore[method-assign]
    client.nft_bids = nft_bids  # type: ignore[method-assign]
    client.list_models = list_models  # type: ignore[method-assign]
    client.model_library = model_library  # type: ignore[method-assign]
    client.publish_nft_package = publish_nft_package  # type: ignore[method-assign]
    client.download_nft_package = download_nft_package  # type: ignore[attr-defined]
    _INSTALLED = True


def _api_url(self: web_bridge.BatikCraftWebClient, path: str) -> str:
    """Accept DRF's absolute pagination URLs, but never follow another origin."""

    text = str(path).strip()
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        base = urllib.parse.urlparse(self.base_url)
        if (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
            raise web_bridge.BatikCraftWebError(
                "Website mengembalikan URL pagination dari host yang berbeda."
            )
        return text
    return _ORIGINAL_API_URL(self, text)


def _request_collection(
    self: web_bridge.BatikCraftWebClient,
    path: str,
) -> list[dict[str, Any]]:
    """Follow every DRF page instead of silently showing only the first 20 rows."""

    items: list[dict[str, Any]] = []
    next_path = str(path)
    visited: set[str] = set()
    for _page in range(1000):
        if next_path in visited:
            raise web_bridge.BatikCraftWebError("Pagination website membentuk loop.")
        visited.add(next_path)
        payload = self._request_json("GET", next_path)
        value = payload.get("results", payload)
        if not isinstance(value, list):
            raise web_bridge.BatikCraftWebError(
                "Daftar marketplace dari website tidak valid."
            )
        items.extend(dict(item) for item in value if isinstance(item, dict))
        raw_next = payload.get("next")
        if not raw_next:
            return items
        next_path = str(raw_next)
    raise web_bridge.BatikCraftWebError("Pagination website melebihi batas aman.")


def capabilities(self: web_bridge.BatikCraftWebClient) -> dict[str, Any]:
    """Read the unauthenticated server contract and supported feature flags."""

    return self._request_json(
        "GET",
        "capabilities/",
        authenticated=False,
    )


def list_nfts(self: web_bridge.BatikCraftWebClient) -> list[dict[str, Any]]:
    return self._request_collection("nfts/")


def nft_bids(
    self: web_bridge.BatikCraftWebClient,
    nft_id: int,
) -> list[dict[str, Any]]:
    return self._request_collection(f"nfts/{int(nft_id)}/bids/")


def list_models(self: web_bridge.BatikCraftWebClient) -> list[dict[str, Any]]:
    return self._request_collection("models/")


def model_library(self: web_bridge.BatikCraftWebClient) -> list[dict[str, Any]]:
    return self._request_collection("library/models/")


def publish_nft_package(
    self: web_bridge.BatikCraftWebClient,
    package_path: str | Path,
    *,
    starting_price: str,
    auction_ends_at: str = "",
) -> dict[str, Any]:
    """Upload both the preview and original editable/licensable NFT package."""

    source = Path(package_path)
    bundle = load_batikcraft_nft(source)
    artwork = dict(bundle.manifest.get("artwork") or {})
    identity = dict(bundle.manifest.get("identity") or {})
    fields: dict[str, str] = {
        "title": str(identity.get("title") or bundle.project.metadata.title),
        "description": str(
            artwork.get("description") or artwork.get("philosophy") or ""
        ),
        "source_project_id": bundle.project.project_id,
        "source_app_version": APP_VERSION,
        "starting_price": str(starting_price),
        "metadata": json.dumps(
            {
                "source_type": "motif_nft",
                "package_id": bundle.package_id,
                "motifs": artwork.get("motifs", []),
                "colors": artwork.get("colors", []),
                "license": artwork.get("license", ""),
                "canvas": artwork.get("canvas", {}),
            },
            ensure_ascii=False,
        ),
    }
    if auction_ends_at.strip():
        fields["auction_ends_at"] = auction_ends_at.strip()
    item = self._request_multipart(
        "POST",
        "nfts/",
        fields=fields,
        files={
            "image": (
                f"{bundle.package_id}.jpg",
                bundle.preview_jpeg,
                "image/jpeg",
            ),
            "package_file": (
                source.name,
                source.read_bytes(),
                mimetypes.guess_type(source.name)[0] or "application/zip",
            ),
        },
    )
    nft_id = int(item["id"])
    return self._request_json("POST", f"nfts/{nft_id}/publish/", payload={})


def download_nft_package(
    self: web_bridge.BatikCraftWebClient,
    nft_id: int,
    destination: str | Path,
) -> Path:
    """Download a source `.batikcraftnft` or `.batikpack` with integrity checking."""

    data, headers = self._request_bytes("GET", f"nfts/{int(nft_id)}/package/")
    target = Path(destination)
    filename = web_bridge._filename_from_disposition(
        headers.get("Content-Disposition", "")
    )
    if target.is_dir():
        target = target / (filename or f"nft-{nft_id}.batikcraftnft")
    elif not target.suffix and filename:
        target = target.with_name(filename)
    target.parent.mkdir(parents=True, exist_ok=True)

    expected = str(headers.get("X-BatikCraft-Package-SHA256") or "").strip().lower()
    if expected:
        import hashlib

        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise web_bridge.BatikCraftWebError(
                "Checksum paket dari BatikCraftWeb tidak cocok."
            )

    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_bytes(data)
    temporary.replace(target)
    return target


__all__ = ["install_web_bridge_extensions"]
