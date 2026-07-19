"""Pustaka aset: isi dari canvas/impor, ekspor paket, dan alur jual."""

from __future__ import annotations

import inspect
from io import BytesIO
from pathlib import Path

from PIL import Image

from batikcraft_studio.assets import AssetLibrary
from batikcraft_studio.assets.builder import AssetCandidate, AssetPackMetadata, build_asset_pack
from batikcraft_studio.assets.personal_store import PERSONAL_PACK_ID, PersonalAssetStore


def _png(color: tuple[int, int, int, int]) -> bytes:
    image = Image.new("RGBA", (48, 48), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_personal_library_fills_and_exports_installable_pack(tmp_path: Path) -> None:
    library = AssetLibrary(tmp_path / "library")
    store = PersonalAssetStore(library)
    store.import_image("ornamen-a.png", _png((120, 40, 20, 255)))
    store.import_image("ornamen-b.png", _png((20, 40, 120, 255)))
    library.refresh()

    records = library.search(pack_id=PERSONAL_PACK_ID)
    assert len(records) == 2

    candidates = [
        AssetCandidate(
            asset_id=record.asset_id,
            name=record.name,
            category=record.category,
            content=library.read_asset(record),
        )
        for record in records
    ]
    metadata = AssetPackMetadata(
        pack_id="user-pack-test",
        name="Paket Uji",
        author="Tester",
    )
    output = build_asset_pack(candidates, metadata, tmp_path / "jual.batikpack")
    assert output.exists() and output.stat().st_size > 0

    # Paket hasil ekspor harus valid dan dapat dipasang kembali.
    installed = library.install_pack(output, replace=True)
    assert installed.name == "Paket Uji"


def test_editor_and_marketplace_expose_asset_library_flow() -> None:
    from batikcraft_studio import batikbrew_context_tool_app as app
    from batikcraft_studio.ui import asset_pack_studio_dialog, context_tool_editor_hotfixes

    editor_source = inspect.getsource(context_tool_editor_hotfixes)
    assert "Simpan Objek Terpilih ke Pustaka Aset" in editor_source
    assert "save_selected_objects_to_library" in editor_source

    app_source = inspect.getsource(app)
    assert "Studio Paket Aset (Buat, Isi, Jual)…" in app_source

    studio_source = inspect.getsource(asset_pack_studio_dialog)
    assert "import_images" in studio_source  # impor gambar dari luar aplikasi
    assert "export_pack" in studio_source
    assert "sell_pack" in studio_source
