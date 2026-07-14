from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from batikcraft_studio.assets import (
    AssetCandidate,
    AssetLibrary,
    AssetPackBuildError,
    AssetPackMetadata,
    build_asset_pack,
    canonicalize_candidate,
    read_review_csv,
    write_review_csv,
)


def _candidate_png() -> bytes:
    image = Image.new("RGBA", (180, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((18, 10, 162, 110), outline=(83, 40, 24, 255), width=12)
    draw.line((45, 60, 135, 60), fill=(139, 90, 43, 255), width=8)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_builder_creates_pack_accepted_by_application_library(tmp_path: Path) -> None:
    candidate = AssetCandidate(
        asset_id="kawung-001",
        name="Kawung Kurasi 001",
        category="motif-pokok",
        content=_candidate_png(),
        tags=("kawung", "geometris", "kurasi"),
        metadata={"source_path": "dataset/kawung/001.png", "confidence": 0.93},
    )
    metadata = AssetPackMetadata(
        pack_id="curated-batik-v1",
        name="Curated Batik V1",
        version="1.0.0",
        author="Balya Rochmadi",
    )

    pack_path = build_asset_pack(
        [candidate],
        metadata,
        tmp_path / "curated-batik-v1.batikpack",
        master_size=512,
        thumbnail_size=128,
    )

    library = AssetLibrary(tmp_path / "library")
    installed = library.install_pack(pack_path)
    assert installed.pack_id == "curated-batik-v1"
    assert len(installed.assets) == 1
    record = installed.assets[0]
    assert record.name == "Kawung Kurasi 001"
    assert record.tags == ("kawung", "geometris", "kurasi")
    assert record.width == 512
    assert record.height == 512
    assert library.read_asset(record).startswith(b"{")
    assert library.read_thumbnail(record).startswith(b"\x89PNG")


def test_canonicalize_trims_and_centers_candidate() -> None:
    candidate = AssetCandidate(
        asset_id="isen-001",
        name="Cecek Uji",
        category="isen-isen",
        content=_candidate_png(),
    )

    prepared = canonicalize_candidate(
        candidate,
        master_size=256,
        padding_ratio=0.1,
        thumbnail_size=96,
    )

    assert prepared.width == 256
    assert prepared.height == 256
    assert prepared.png.startswith(b"\x89PNG")
    assert prepared.thumbnail.startswith(b"\x89PNG")
    with Image.open(BytesIO(prepared.png)) as image:
        assert image.size == (256, 256)
        assert image.getchannel("A").getbbox() is not None


def test_review_csv_round_trip_loads_only_accepted_candidates(tmp_path: Path) -> None:
    candidate_root = tmp_path / "candidates"
    candidate_root.mkdir()
    accepted = AssetCandidate(
        asset_id="accepted-001",
        name="Diterima",
        category="ornamen",
        content=_candidate_png(),
        tags=("hias",),
        metadata={"source_path": "a.png", "confidence": 0.9},
    )
    rejected = AssetCandidate(
        asset_id="rejected-001",
        name="Ditolak",
        category="lainnya",
        content=_candidate_png(),
    )
    (candidate_root / "accepted-001.png").write_bytes(accepted.content)
    (candidate_root / "rejected-001.png").write_bytes(rejected.content)
    review_path = write_review_csv([accepted, rejected], tmp_path / "review.csv")
    text = review_path.read_text(encoding="utf-8")
    review_path.write_text(
        text.replace("1,rejected-001", "0,rejected-001"),
        encoding="utf-8",
    )

    loaded = read_review_csv(review_path, candidate_root)

    assert [item.asset_id for item in loaded] == ["accepted-001"]
    assert loaded[0].tags == ("hias",)


def test_builder_rejects_duplicate_ids_and_empty_pack(tmp_path: Path) -> None:
    candidate = AssetCandidate(
        asset_id="same-id",
        name="Sama",
        category="ornamen",
        content=_candidate_png(),
    )
    metadata = AssetPackMetadata(pack_id="test", name="Test")

    with pytest.raises(AssetPackBuildError, match="unik"):
        build_asset_pack([candidate, candidate], metadata, tmp_path / "duplicate.batikpack")
    with pytest.raises(AssetPackBuildError, match="Tidak ada"):
        build_asset_pack([], metadata, tmp_path / "empty.batikpack")


def test_kaggle_notebook_is_valid_and_uses_shared_pipeline() -> None:
    notebook_path = (
        Path(__file__).parents[1]
        / "notebooks"
        / "kaggle_batik_asset_pack_builder.ipynb"
    )
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))

    assert notebook["nbformat"] == 4
    assert len(notebook["cells"]) >= 10
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )
    assert "kaggle_asset_pipeline" in source
    assert "build_curated_pack" in source
    assert "Asset → Install Asset Pack" in source
