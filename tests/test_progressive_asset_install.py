from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path
from threading import Event

import pytest
from PIL import Image, ImageDraw

from batikcraft_studio.assets import AssetLibrary
from batikcraft_studio.assets.progressive_install import (
    AssetInstallCancelled,
    AssetInstallProgress,
    install_pack_with_progress,
)
from batikcraft_studio.imaging import EditableBatikAsset, encode_batik_asset


def _png(index: int) -> bytes:
    image = Image.new("RGBA", (128, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    inset = 8 + index
    draw.ellipse(
        (inset, inset, 127 - inset, 95 - inset),
        outline=(70 + index, 38, 24, 255),
        width=7,
    )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _write_pack(path: Path, *, count: int = 4, pack_id: str = "large-demo") -> None:
    assets = []
    encoded: dict[str, bytes] = {}
    thumbnails: dict[str, bytes] = {}
    for index in range(count):
        asset_id = f"outline-{index:03d}"
        png = _png(index)
        asset = EditableBatikAsset(
            name=f"Outline {index}",
            category="ornamen",
            content=png,
            width=128,
            height=96,
            metadata={"index": index},
        )
        asset_path = f"assets/{asset_id}.batikasset"
        thumbnail_path = f"thumbnails/{asset_id}.png"
        encoded[asset_path] = encode_batik_asset(asset)
        thumbnails[thumbnail_path] = png
        assets.append(
            {
                "id": asset_id,
                "name": asset.name,
                "category": asset.category,
                "file": asset_path,
                "thumbnail": thumbnail_path,
                "tags": ["outline", "test"],
                "width": asset.width,
                "height": asset.height,
                "metadata": {"index": index},
            }
        )
    manifest = {
        "format": "batikcraft-asset-pack",
        "schema_version": "1.0",
        "pack": {
            "id": pack_id,
            "name": "Large Demo",
            "version": "1.0.0",
        },
        "assets": assets,
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for relative_path, content in encoded.items():
            archive.writestr(relative_path, content)
        for relative_path, content in thumbnails.items():
            archive.writestr(relative_path, content)


def test_progressive_install_reports_monotonic_real_progress(tmp_path: Path) -> None:
    archive_path = tmp_path / "large.batikpack"
    _write_pack(archive_path, count=5)
    library = AssetLibrary(tmp_path / "library")
    updates: list[AssetInstallProgress] = []

    pack = install_pack_with_progress(
        library,
        archive_path,
        progress=updates.append,
    )

    assert pack.pack_id == "large-demo"
    assert len(pack.assets) == 5
    assert updates[0].stage == "opening"
    assert updates[-1].stage == "complete"
    assert updates[-1].fraction == 1.0
    assert any(update.stage == "extracting" for update in updates)
    assert any(update.stage == "validating" for update in updates)
    assert any(update.stage == "committing" for update in updates)
    fractions = [update.fraction for update in updates]
    assert fractions == sorted(fractions)


def test_cancelling_before_commit_leaves_no_partial_pack(tmp_path: Path) -> None:
    archive_path = tmp_path / "cancel.batikpack"
    _write_pack(archive_path, count=6, pack_id="cancel-demo")
    library = AssetLibrary(tmp_path / "library")
    cancel_event = Event()

    def cancel_during_extract(update: AssetInstallProgress) -> None:
        if update.stage == "extracting" and update.current > 0:
            cancel_event.set()

    with pytest.raises(AssetInstallCancelled, match="dibatalkan"):
        install_pack_with_progress(
            library,
            archive_path,
            progress=cancel_during_extract,
            cancel_event=cancel_event,
        )

    library.refresh()
    assert library.packs == ()
    assert not (library.root / "cancel-demo").exists()
    assert not (library.root / ".cancel-demo.backup").exists()
