from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from batikcraft_studio.assets import AssetLibrary, AssetLibraryError
from batikcraft_studio.imaging import EditableBatikAsset, encode_batik_asset


def _png(color: tuple[int, int, int, int] = (96, 47, 27, 255)) -> bytes:
    image = Image.new("RGBA", (96, 72), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 6, 88, 66), outline=color, width=8)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _write_pack(
    path: Path,
    *,
    pack_id: str = "batik-demo",
    name: str = "Batik Demo",
    version: str = "1.0.0",
    asset_name: str = "Kawung Demo",
) -> None:
    asset = EditableBatikAsset(
        name=asset_name,
        category="motif-pokok",
        content=_png(),
        width=96,
        height=72,
        metadata={"daerah": "uji", "source": "dataset"},
    )
    manifest = {
        "format": "batikcraft-asset-pack",
        "schema_version": "1.0",
        "pack": {
            "id": pack_id,
            "name": name,
            "version": version,
            "author": "Test",
            "description": "Pack untuk pengujian",
        },
        "assets": [
            {
                "id": "kawung-001",
                "name": asset_name,
                "category": "motif-pokok",
                "file": "assets/kawung-001.batikasset",
                "thumbnail": "thumbnails/kawung-001.png",
                "tags": ["kawung", "geometris", "dataset"],
                "width": 96,
                "height": 72,
                "metadata": {"source_index": 1},
            }
        ],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("assets/kawung-001.batikasset", encode_batik_asset(asset))
        archive.writestr("thumbnails/kawung-001.png", _png())


def test_install_search_read_and_uninstall_asset_pack(tmp_path: Path) -> None:
    archive_path = tmp_path / "demo.batikpack"
    _write_pack(archive_path)
    library = AssetLibrary(tmp_path / "library")

    pack = library.install_pack(archive_path)

    assert pack.pack_id == "batik-demo"
    assert library.asset_count == 1
    assert (library.root / "batik-demo" / "manifest.json").is_file()
    result = library.search("kawung", category="motif-pokok")
    assert len(result) == 1
    assert result[0].name == "Kawung Demo"
    assert result[0].tags == ("kawung", "geometris", "dataset")
    assert library.read_asset(result[0]).startswith(b"{")
    assert library.read_thumbnail(result[0]).startswith(b"\x89PNG")

    library.uninstall_pack("batik-demo")
    assert library.asset_count == 0
    assert not (library.root / "batik-demo").exists()


def test_install_requires_replace_for_existing_pack(tmp_path: Path) -> None:
    first = tmp_path / "first.batikpack"
    second = tmp_path / "second.batikpack"
    _write_pack(first, version="1.0.0", asset_name="Kawung Awal")
    _write_pack(second, version="2.0.0", asset_name="Kawung Baru")
    library = AssetLibrary(tmp_path / "library")
    library.install_pack(first)

    with pytest.raises(AssetLibraryError, match="sudah terpasang"):
        library.install_pack(second)

    replaced = library.install_pack(second, replace=True)
    assert replaced.version == "2.0.0"
    assert library.search("baru")[0].name == "Kawung Baru"


def test_search_filters_pack_category_and_limits_results(tmp_path: Path) -> None:
    first = tmp_path / "first.batikpack"
    second = tmp_path / "second.batikpack"
    _write_pack(first, pack_id="first", name="First Pack", asset_name="Kawung Satu")
    _write_pack(second, pack_id="second", name="Second Pack", asset_name="Kawung Dua")
    library = AssetLibrary(tmp_path / "library")
    library.install_pack(first)
    library.install_pack(second)

    assert len(library.search("kawung")) == 2
    assert len(library.search(category="motif-pokok", pack_id="first")) == 1
    assert library.search("kawung", limit=1)[0].category == "motif-pokok"
    assert library.search(category="isen-isen") == ()


def test_install_rejects_path_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.batikpack"
    manifest = {
        "format": "batikcraft-asset-pack",
        "schema_version": "1.0",
        "pack": {"id": "unsafe", "name": "Unsafe", "version": "1"},
        "assets": [
            {
                "id": "bad",
                "name": "Bad",
                "category": "ornamen",
                "file": "../outside.png",
            }
        ],
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("../outside.png", _png())

    library = AssetLibrary(tmp_path / "library")
    with pytest.raises(AssetLibraryError, match="tidak aman"):
        library.install_pack(archive_path)
    assert not (tmp_path / "outside.png").exists()


def test_refresh_skips_invalid_installed_directories(tmp_path: Path) -> None:
    root = tmp_path / "library"
    (root / "broken").mkdir(parents=True)
    (root / "broken" / "manifest.json").write_text("not json", encoding="utf-8")

    library = AssetLibrary(root)

    assert library.packs == ()
    assert library.asset_count == 0
