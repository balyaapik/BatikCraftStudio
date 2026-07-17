from __future__ import annotations

import inspect
import json
import zipfile

import pytest

from batikcraft_studio import batikbrew_context_tool_app
from batikcraft_studio.web_bridge import (
    BatikCraftWebError,
    inspect_model_pack,
    normalize_base_url,
)


def test_normalize_web_base_url_removes_api_suffix() -> None:
    assert normalize_base_url("https://example.com/api/v1/") == "https://example.com"
    assert normalize_base_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"


def test_normalize_web_base_url_rejects_invalid_value() -> None:
    with pytest.raises(BatikCraftWebError):
        normalize_base_url("example.com")


def test_inspect_model_pack_reads_manifest(tmp_path) -> None:
    path = tmp_path / "ornament.batikmodel"
    manifest = {
        "format": "batikcraft-model-pack",
        "model": {
            "model_id": "ornament-v1",
            "name": "Ornament V1",
            "version": "1.0.0",
            "base_model_family": "sdxl",
            "trigger_words": ["bcr_ornament"],
            "capabilities": ["ornament"],
        },
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))

    assert inspect_model_pack(path)["model"]["model_id"] == "ornament-v1"


def test_ai_batik_menu_exposes_account_and_marketplace_actions() -> None:
    source = inspect.getsource(batikbrew_context_tool_app.ContextToolApplication)
    assert "Login / Akun BatikCraftWeb" in source
    assert "NFT Marketplace" in source
    assert "Model Marketplace" in source
    assert "Publish Motif sebagai NFT" in source
    assert "Publish Model ke Marketplace" in source
