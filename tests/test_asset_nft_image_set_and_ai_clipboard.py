from __future__ import annotations

import inspect
import json
from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from batikcraft_studio import __main__
from batikcraft_studio.integrated_market_app import ContextToolApplication
from batikcraft_studio.ui import batikbrew_variation_dialog
from batikcraft_studio.ui.generated_image_clipboard import get_generated_image_clipboard
from batikcraft_studio.ui.image_set_dataset_dialog import (
    caption_for_image,
    discover_image_files,
)
from batikcraft_studio.ui.library_asset_nft_dialog import publish_library_asset_nft


def _png() -> bytes:
    image = Image.new("RGBA", (48, 36), (112, 64, 42, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_image_set_discovers_images_but_never_batikasset(tmp_path) -> None:
    (tmp_path / "motif-one.png").write_bytes(_png())
    (tmp_path / "motif-two.jpg").write_bytes(_png())
    (tmp_path / "legacy.batikasset").write_text("{}", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "motif-three.webp").write_bytes(_png())

    recursive = discover_image_files(tmp_path, recursive=True)
    flat = discover_image_files(tmp_path, recursive=False)

    assert {path.name for path in recursive} == {
        "motif-one.png",
        "motif-two.jpg",
        "motif-three.webp",
    }
    assert {path.name for path in flat} == {"motif-one.png", "motif-two.jpg"}
    assert all(path.suffix != ".batikasset" for path in recursive)


def test_image_set_caption_prefers_utf8_sidecar(tmp_path) -> None:
    image = tmp_path / "ornamen_anggrek.png"
    image.write_bytes(_png())
    assert caption_for_image(image) == "ornamen anggrek"

    image.with_suffix(".txt").write_text(
        "single orchid batik ornament, canting line art",
        encoding="utf-8",
    )
    assert caption_for_image(image) == "single orchid batik ornament, canting line art"


def test_generated_image_clipboard_round_trip() -> None:
    clipboard = get_generated_image_clipboard()
    clipboard.clear()
    payload = clipboard.copy(
        _png(),
        name="BatikBrew Variation",
        metadata={"seed": 2026},
    )

    assert clipboard.has_image is True
    assert clipboard.read() == payload
    assert payload.width == 48
    assert payload.height == 36
    assert payload.metadata["seed"] == 2026
    clipboard.clear()
    assert clipboard.read() is None


def test_library_asset_nft_uses_existing_nft_api_with_asset_metadata() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.multipart = None
            self.publish = None

        def _request_multipart(self, method, path, *, fields, files):
            self.multipart = (method, path, fields, files)
            return {"id": 17}

        def _request_json(self, method, path, *, payload):
            self.publish = (method, path, payload)
            return {"id": 17, "title": "Asset NFT", "status": "listed"}

    client = FakeClient()
    project = SimpleNamespace(project_id="project-001")
    asset = SimpleNamespace(
        object_id="object-001",
        name="Ornamen Anggrek",
        kind=SimpleNamespace(value="raster"),
        properties={"asset_category": "ornamen"},
    )

    result = publish_library_asset_nft(
        client,
        project=project,
        asset=asset,
        content=_png(),
        title="Asset NFT",
        description="Ornamen untuk koleksi digital.",
        starting_price="50000",
    )

    assert result["status"] == "listed"
    method, path, fields, files = client.multipart
    assert (method, path) == ("POST", "nfts/")
    metadata = json.loads(fields["metadata"])
    assert metadata["source_type"] == "library_asset"
    assert metadata["asset_category"] == "ornamen"
    assert metadata["project_id"] == "project-001"
    assert files["image"][2] == "image/png"
    assert client.publish == ("POST", "nfts/17/publish/", {})


def test_integrated_entrypoint_exposes_requested_menu_and_shortcuts() -> None:
    main_source = inspect.getsource(__main__)
    app_source = inspect.getsource(ContextToolApplication)
    variation_source = inspect.getsource(batikbrew_variation_dialog.BatikBrewVariationDialog)

    assert "integrated_market_app" in main_source
    assert "Generate Motif BatikBrew…" in app_source
    assert "Jual Asset Pustaka sebagai NFT…" in app_source
    assert "Set Gambar Training SDXL…" in app_source
    assert "OBJECT_COPY_SEQUENCE" in app_source
    assert "OBJECT_PASTE_SEQUENCE" in app_source
    assert "Salin Variasi (Ctrl+C)" in variation_source
    assert "get_generated_image_clipboard" in variation_source
