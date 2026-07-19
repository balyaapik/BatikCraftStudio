"""Pustaka aset: wadah bermetadata dulu, lalu isi, lalu ekspor/jual."""

from __future__ import annotations

import inspect
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from batikcraft_studio.assets import AssetLibrary, AssetLibraryError
from batikcraft_studio.assets.builder import AssetCandidate, AssetPackMetadata, build_asset_pack
from batikcraft_studio.assets.personal_store import (
    PersonalAssetStore,
    create_user_library,
    list_user_libraries,
    parse_library_description,
)


def _png(color: tuple[int, int, int, int]) -> bytes:
    image = Image.new("RGBA", (48, 48), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_import_requires_existing_library_container(tmp_path: Path) -> None:
    library = AssetLibrary(tmp_path / "library")
    store = PersonalAssetStore(library)
    with pytest.raises(AssetLibraryError, match="Buat pustaka dulu"):
        store.import_image("x.png", _png((1, 2, 3, 255)), pack_id="userlib-belum-ada")


def test_create_library_then_fill_then_export(tmp_path: Path) -> None:
    library = AssetLibrary(tmp_path / "library")
    store = PersonalAssetStore(library)

    pack_id = create_user_library(
        library,
        name="Pustaka Parang",
        author="Balya",
        philosophy="Keteguhan dan kesinambungan",
        library_type="motif-pokok",
    )
    packs = list_user_libraries(library)
    assert [pack.name for pack in packs] == ["Pustaka Parang"]
    library_type, philosophy = parse_library_description(packs[0].description)
    assert library_type == "motif-pokok"
    assert philosophy == "Keteguhan dan kesinambungan"
    assert packs[0].author == "Balya"

    store.import_image("parang-1.png", _png((120, 40, 20, 255)), category="motif-pokok", pack_id=pack_id)
    store.import_image("parang-2.png", _png((20, 40, 120, 255)), category="motif-pokok", pack_id=pack_id)
    library.refresh()
    records = library.search(pack_id=pack_id)
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
    pack = library.get_pack(pack_id)
    metadata = AssetPackMetadata(
        pack_id=pack.pack_id, name=pack.name, author=pack.author, description=pack.description
    )
    output = build_asset_pack(candidates, metadata, tmp_path / "jual.batikpack")
    installed = library.install_pack(output, replace=True)
    assert installed.name == "Pustaka Parang"


def test_asset_menu_hosts_all_library_functions() -> None:
    from batikcraft_studio import batikbrew_context_tool_app as app
    from batikcraft_studio.ui import asset_pack_studio_dialog, context_tool_editor_hotfixes

    app_source = inspect.getsource(app)
    # Semua fungsi pustaka masuk menu Asset, bukan Marketplace.
    assert "_extend_asset_menu" in app_source
    assert "Buat Pustaka Aset Baru…" in app_source
    assert "Studio Pustaka Aset (Isi, Kelola, Jual)…" in app_source
    assert "Simpan Objek Terpilih ke Pustaka…" in app_source
    assert "Studio Paket Aset (Buat, Isi, Jual)…" not in app_source

    studio_source = inspect.getsource(asset_pack_studio_dialog)
    assert "CreateLibraryDialog" in studio_source
    assert "Filosofi" in studio_source
    assert "LIBRARY_TYPES" in studio_source

    editor_source = inspect.getsource(context_tool_editor_hotfixes)
    assert "Buat wadah pustaka dulu" in editor_source or "Buat pustaka dulu" in editor_source
